"""
Zabbix API client. Extracted from the original Streamlit app.
All API call logic, payloads, and parsing are preserved as-is.
Only change: st.progress/st.warning replaced with logging.
"""

import datetime
import re
import time
import logging
import requests
import urllib3
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from sklearn.linear_model import LinearRegression

from config import settings

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger(__name__)

SEV_MAP = {
    '0': 'Not Classified', '1': 'Info', '2': 'Warning',
    '3': 'Average', '4': 'High', '5': 'Disaster'
}


class ZabbixAPIError(Exception):
    pass


class ZabbixClient:
    """
    Unified Zabbix API client.
    Mirrors the original fetch_zabbix_* functions exactly.
    """

    def __init__(self, url: str, token: str):
        self.url = url
        self.token = token
        self.session = requests.Session()
        # Kept as-is per user request: no SSL verification
        self.session.verify = settings.zabbix_verify_tls
        self.session.headers.update({"Content-Type": "application/json"})
        # Connection pooling — reuse TCP connections across calls
        adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=10,
            max_retries=Retry(total=2, backoff_factor=2,
                              status_forcelist=[502, 503, 504])
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _call(self, method: str, params: dict, timeout: int = None, req_id: int = 1, retries: int = 2) -> list:
        if timeout is None:
            timeout = settings.api_timeout_medium
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "auth": self.token,
            "id": req_id
        }
        last_err = None
        for attempt in range(1, retries + 2):  # retries + 1 total attempts
            try:
                resp = self.session.post(self.url, json=payload, timeout=timeout)
                resp.raise_for_status()
                result = resp.json()
                if "error" in result:
                    raise ZabbixAPIError(f"Zabbix API error: {result['error']}")
                return result.get("result", [])
            except (requests.exceptions.Timeout,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.HTTPError) as e:
                # Only retry server errors (5xx), not client errors (4xx)
                if isinstance(e, requests.exceptions.HTTPError):
                    if e.response is not None and e.response.status_code < 500:
                        raise ZabbixAPIError(
                            f"Zabbix API {method} returned HTTP {e.response.status_code}: {e}"
                        )
                last_err = e
                if attempt <= retries:
                    wait = 5 * attempt  # 5s, 10s backoff
                    logger.warning("Zabbix %s attempt %d/%d failed (%s), retrying in %ds...",
                                   method, attempt, retries + 1, type(e).__name__, wait)
                    time.sleep(wait)
                else:
                    logger.error("Zabbix %s failed after %d attempts: %s", method, retries + 1, last_err)
        raise ZabbixAPIError(f"Zabbix API {method} timed out after {retries + 1} attempts: {last_err}")

    def resolve_group_id(self, group_name: str) -> str:
        groups = self._call("hostgroup.get", {
            "output": "extend",
            "filter": {"name": [group_name]}
        })
        if not groups:
            raise ZabbixAPIError(f"Group '{group_name}' not found")
        return groups[0]["groupid"]

    def fetch_hosts_and_tags(self, group_id: str) -> dict:
        """Returns {hostname: [tag:value, ...]}"""
        hosts = self._call("host.get", {
            "output": ["hostid", "name"],
            "groupids": group_id,
            "selectTags": "extend"
        }, req_id=99)
        tag_map = {}
        for h in hosts:
            tags = [f"{t['tag']}:{t['value']}" for t in h.get("tags", [])]
            tag_map[h["name"]] = tags
        return tag_map

    def fetch_capacity_trends(self, group_id: str, days: int) -> pd.DataFrame:
        """
        Fetches 30-day hourly trends for CPU/Memory from Zabbix
        and resamples to daily averages for forecasting.
        Replaces the original fetch_zabbix_capacity_trends.
        """
        try:
            items = self._call("item.get", {
                "output": ["itemid", "hostid", "key_", "name"],
                "groupids": group_id,
                "search": {"key_": ["system.cpu.util", "vm.memory.util"]},
                "searchByAny": True,
                "selectHosts": ["name"]
            }, timeout=settings.api_timeout_long, req_id=500)

            if not items:
                return pd.DataFrame()

            item_map = {}
            for i in items:
                h_name = i["hosts"][0]["name"] if i.get("hosts") else "Unknown"
                k = i["key_"]
                m_type = "CPU" if "cpu" in k else "Memory"
                item_map[i["itemid"]] = {"host": h_name, "metric": m_type}

            item_ids = list(item_map.keys())
            time_from = int((datetime.datetime.now() - datetime.timedelta(days=days)).timestamp())
            all_trends = []

            # Parallel chunk fetches
            chunks = [item_ids[i:i + settings.trend_chunk_size]
                      for i in range(0, len(item_ids), settings.trend_chunk_size)]
            logger.info("Capacity trends: %d items in %d chunks (parallel)", len(item_ids), len(chunks))

            def _fetch_trend_chunk(idx_chunk):
                idx, chunk = idx_chunk
                return self._call("trend.get", {
                    "output": ["itemid", "clock", "value_avg"],
                    "itemids": chunk,
                    "time_from": time_from,
                    "limit": "5000"
                }, timeout=settings.api_timeout_medium, req_id=600 + idx)

            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = {pool.submit(_fetch_trend_chunk, (i, c)): i
                           for i, c in enumerate(chunks)}
                try:
                    for future in as_completed(futures, timeout=settings.fetch_stage_timeout_seconds):
                        try:
                            all_trends.extend(future.result(timeout=30))
                        except TimeoutError:
                            logger.warning("Trend chunk %d timed out", futures[future])
                        except Exception as e:
                            logger.warning("Trend chunk %d failed: %s", futures[future], e)
                except TimeoutError:
                    logger.warning("Capacity trend chunks exceeded stage timeout — continuing with partial data")

            if not all_trends:
                return pd.DataFrame()

            trend_rows = []
            for t in all_trends:
                iid = t["itemid"]
                if iid in item_map:
                    meta = item_map[iid]
                    trend_rows.append({
                        "Date": datetime.datetime.fromtimestamp(int(t["clock"])),
                        "Server Name": meta["host"],
                        "Metric": meta["metric"],
                        "Utilization": float(t["value_avg"])
                    })

            df = pd.DataFrame(trend_rows)
            if not df.empty:
                df["Date"] = pd.to_datetime(df["Date"]).dt.date
                today = datetime.date.today()
                df = df[df["Date"] < today]
                df_daily = df.groupby(
                    ["Date", "Server Name", "Metric"], as_index=False
                )["Utilization"].mean()
                df_daily["Date"] = pd.to_datetime(df_daily["Date"])
                return df_daily
            return pd.DataFrame()

        except ZabbixAPIError:
            raise
        except Exception as e:
            logger.warning("Capacity trend fetch warning: %s", e)
            return pd.DataFrame()

    def fetch_db_trends(self, group_id: str, days: int) -> pd.DataFrame:
        """Replaces fetch_zabbix_db_trends. Identical logic."""
        try:
            # MSSQL items
            items = self._call("item.get", {
                "output": ["itemid", "hostid", "key_", "lastvalue", "value_type"],
                "groupids": group_id,
                "search": {"key_": "mssql.db.data_files_size*"},
                "searchWildcardsEnabled": True,
                "selectHosts": ["name"]
            }, timeout=settings.api_timeout_long, req_id=105)

            # PostgreSQL items
            items += self._call("item.get", {
                "output": ["itemid", "hostid", "key_", "lastvalue", "value_type"],
                "groupids": group_id,
                "search": {"key_": "pgsql.db.size*"},
                "searchWildcardsEnabled": True,
                "selectHosts": ["name"]
            }, timeout=settings.api_timeout_long, req_id=106)

            if not items:
                return pd.DataFrame()

            item_ids = [i["itemid"] for i in items]
            time_from = int((datetime.datetime.now() - datetime.timedelta(days=days)).timestamp())

            hist_data = {}
            chunks = [item_ids[i:i + settings.trend_chunk_size]
                      for i in range(0, len(item_ids), settings.trend_chunk_size)]
            logger.info("DB trends: %d items in %d chunks (parallel)", len(item_ids), len(chunks))

            def _fetch_db_chunk(idx_chunk):
                idx, chunk = idx_chunk
                return self._call("trend.get", {
                    "output": ["itemid", "clock", "value_avg"],
                    "itemids": chunk,
                    "time_from": time_from
                }, timeout=settings.api_timeout_medium, req_id=107 + idx)

            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = {pool.submit(_fetch_db_chunk, (i, c)): i
                           for i, c in enumerate(chunks)}
                try:
                    for future in as_completed(futures, timeout=settings.fetch_stage_timeout_seconds):
                        try:
                            for h in future.result(timeout=30):
                                iid = h["itemid"]
                                if iid not in hist_data:
                                    hist_data[iid] = []
                                hist_data[iid].append((int(h["clock"]), float(h["value_avg"])))
                        except TimeoutError:
                            logger.warning("DB trend chunk %d timed out", futures[future])
                        except Exception as e:
                            logger.warning("DB trend chunk %d failed: %s", futures[future], e)
                except TimeoutError:
                    logger.warning("DB trend chunks exceeded stage timeout — continuing with partial data")

            results = []
            for item in items:
                key = item.get("key_", "")
                match = re.search(r'\["?([^"\]]+)"?\]', key)
                db_name = match.group(1) if match else "Instance Total"
                host_name = item["hosts"][0]["name"] if item.get("hosts") else "Unknown"
                db_type = "MSSQL" if "mssql" in key else "PostgreSQL"
                history = hist_data.get(item["itemid"], [])

                try:
                    raw_size_bytes = float(item.get("lastvalue", 0))
                except (ValueError, TypeError):
                    raw_size_bytes = 0.0

                growth_rate_bytes = 0.0
                suggestion = "Stable"
                trend_line = []

                if len(history) > 1:
                    df_hist = pd.DataFrame(history, columns=["ts", "val"])
                    trend_line = (df_hist["val"] / (1024 ** 3)).tolist()
                    reg = LinearRegression()
                    reg.fit(df_hist["ts"].values.reshape(-1, 1), df_hist["val"].values)
                    growth_rate_bytes = reg.coef_[0] * 86400
                    growth_gb = growth_rate_bytes / (1024 ** 3)
                    if growth_gb > 1.0:
                        suggestion = "High Growth"
                    elif growth_gb > 0.1:
                        suggestion = "Steady"
                    elif growth_gb < -0.01:
                        suggestion = "Shrinking"
                    else:
                        suggestion = "Stable"

                results.append({
                    "Server Name": host_name,
                    "Database Name": db_name,
                    "Type": db_type,
                    "Raw Size": raw_size_bytes,
                    "Raw Growth": growth_rate_bytes,
                    "Utilization Suggestion": suggestion,
                    "Trend": trend_line
                })

            return pd.DataFrame(results)

        except ZabbixAPIError:
            raise
        except Exception as e:
            logger.warning("DB trend warning: %s", e)
            return pd.DataFrame()

    def fetch_disk_usage(self, group_id: str) -> pd.DataFrame:
        """Replaces fetch_zabbix_disk_usage. Identical logic."""
        from services.disk_classifier import classify_drive, calculate_disk_risk

        try:
            items = self._call("item.get", {
                "output": ["key_", "lastvalue", "hostid"],
                "groupids": group_id,
                "search": {"key_": "vfs.fs.size*"},
                "searchWildcardsEnabled": True,
                "selectHosts": ["name"]
            }, timeout=settings.api_timeout_long, req_id=110)

            host_data = {}
            for i in items:
                key = i["key_"]
                host = i["hosts"][0]["name"] if i.get("hosts") else "Unknown"
                try:
                    val = float(i.get("lastvalue", 0))
                except (ValueError, TypeError):
                    val = 0

                match = re.search(r'vfs\.fs\.size\[(.*?),(.*?)\]', key)
                if match:
                    drive, mode = match.group(1), match.group(2)
                    if host not in host_data:
                        host_data[host] = {}
                    if drive not in host_data[host]:
                        host_data[host][drive] = {"total": 0, "used": 0}
                    if mode == "total":
                        host_data[host][drive]["total"] = val
                    elif mode == "used":
                        host_data[host][drive]["used"] = val

            rows = []
            for host, drives in host_data.items():
                for drive, metrics in drives.items():
                    total_gb = metrics["total"] / (1024 ** 3)
                    used_gb = metrics["used"] / (1024 ** 3)
                    if total_gb > 0:
                        free_gb = total_gb - used_gb
                        pct_used = (used_gb / total_gb) * 100
                        d_type = classify_drive(drive)
                        risk_cat, action = calculate_disk_risk(d_type, used_gb, total_gb)
                        rows.append({
                            "Server Name": host, "Drive": drive, "Type": d_type,
                            "Total Size (GB)": round(total_gb, 1),
                            "Used (GB)": round(used_gb, 1),
                            "Free (GB)": round(free_gb, 1),
                            "Utilization %": round(pct_used, 1),
                            "Risk Category": risk_cat,
                            "Action Required": action
                        })

            return pd.DataFrame(rows)

        except Exception as e:
            logger.error("Disk fetch error: %s", e)
            return pd.DataFrame()

    def fetch_hardware(self, group_id: str) -> pd.DataFrame:
        """Replaces fetch_zabbix_hardware. Identical logic."""
        try:
            items = self._call("item.get", {
                "output": ["key_", "lastvalue", "hostid"],
                "groupids": group_id,
                "search": {"key_": [
                    "system.cpu.num", "vm.memory.size[total]",
                    "system.cpu.util", "vm.memory.util"
                ]},
                "searchByAny": True,
                "selectHosts": ["name"]
            }, timeout=settings.api_timeout_medium, req_id=115)

            host_hw = {}
            for i in items:
                host = i["hosts"][0]["name"] if i.get("hosts") else "Unknown"
                try:
                    val = float(i.get("lastvalue", 0))
                except (ValueError, TypeError):
                    val = 0
                key = i["key_"]
                if host not in host_hw:
                    host_hw[host] = {
                        "CPU_Count": 0, "RAM_GB": 0,
                        "Zab_CPU_Util": 0, "Zab_Mem_Util": 0
                    }
                if "system.cpu.num" in key:
                    host_hw[host]["CPU_Count"] = int(val)
                elif "vm.memory.size" in key:
                    host_hw[host]["RAM_GB"] = round(val / (1024 ** 3), 1)
                elif "system.cpu.util" in key:
                    host_hw[host]["Zab_CPU_Util"] = val
                elif "vm.memory.util" in key:
                    host_hw[host]["Zab_Mem_Util"] = val

            return pd.DataFrame([
                {"Server Name": h, **d} for h, d in host_hw.items()
            ])

        except Exception as e:
            logger.warning("Hardware fetch warning: %s", e)
            return pd.DataFrame()

    def _map_triggers_to_hosts(self, trigger_ids: list) -> dict:
        """Replaces map_triggers_to_hosts. Identical logic."""
        trigger_map = {}
        unique_ids = list(set(trigger_ids))
        chunks = [unique_ids[i:i + 500] for i in range(0, len(unique_ids), 500)]
        logger.info("Trigger mapping: %d triggers in %d chunks (parallel)", len(unique_ids), len(chunks))

        def _fetch_trigger_chunk(idx_chunk):
            idx, chunk = idx_chunk
            return self._call("trigger.get", {
                "output": ["triggerid"],
                "triggerids": chunk,
                "selectHosts": ["hostid", "name"]
            }, timeout=settings.api_timeout_medium, req_id=800 + idx)

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(_fetch_trigger_chunk, (i, c)): i
                       for i, c in enumerate(chunks)}
            try:
                for future in as_completed(futures, timeout=settings.fetch_stage_timeout_seconds):
                    try:
                        for t in future.result(timeout=30):
                            if t.get("hosts"):
                                trigger_map[t["triggerid"]] = t["hosts"][0]["name"]
                    except TimeoutError:
                        logger.warning("Trigger chunk %d timed out", futures[future])
                    except Exception:
                        continue
            except TimeoutError:
                logger.warning("Trigger mapping exceeded stage timeout — continuing with partial data")
        return trigger_map

    def fetch_problems_and_events(self, group_id: str, days: int) -> "tuple[pd.DataFrame, pd.DataFrame]":
        """
        Fetches both active problems and event history.
        Returns (problems_df, events_df).
        Compatible with Zabbix 7.0+ (no selectHosts on problem/event.get).
        """
        time_from = int((datetime.datetime.now() - datetime.timedelta(days=days)).timestamp())

        # Active problems (no selectHosts — removed in Zabbix 7.0)
        problems = self._call("problem.get", {
            "output": "extend",
            "groupids": group_id,
            "severities": [2, 3, 4, 5],
            "time_from": time_from,
            "sortfield": ["eventid"],
            "sortorder": "DESC",
        }, req_id=2)

        # Event history (for trends)
        trend_days = max(days, 15)
        time_from_trend = int(
            (datetime.datetime.now() - datetime.timedelta(days=trend_days)).timestamp()
        )
        events = self._call("event.get", {
            "output": ["eventid", "clock", "name", "severity", "objectid"],
            "groupids": group_id,
            "time_from": time_from_trend,
            "source": 0, "object": 0, "value": 1,
            "sortfield": "clock", "sortorder": "DESC",
        }, req_id=4)

        # Resolve all hosts via trigger → host mapping
        all_trigger_ids = []
        for p in problems:
            all_trigger_ids.append(p["objectid"])
        for e in events:
            all_trigger_ids.append(e["objectid"])

        trigger_host_map = {}
        if all_trigger_ids:
            trigger_host_map = self._map_triggers_to_hosts(all_trigger_ids)

        def resolve_host(record):
            return trigger_host_map.get(record["objectid"], "Unknown")

        # Build DataFrames
        problem_data = [{
            "Date": datetime.datetime.fromtimestamp(int(p["clock"])),
            "Server Name": resolve_host(p),
            "Problem Name": p["name"],
            "Severity": SEV_MAP.get(p["severity"], "Unknown")
        } for p in problems]

        event_data = [{
            "Date": datetime.datetime.fromtimestamp(int(e["clock"])),
            "Server Name": resolve_host(e),
            "Problem Name": e["name"],
            "Severity": SEV_MAP.get(e["severity"], "Unknown")
        } for e in events]

        return pd.DataFrame(problem_data), pd.DataFrame(event_data)

    def fetch_all(self, group_name: str, days: int, progress_callback=None) -> dict:
        """
        Unified fetch — replaces fetch_zabbix_live.
        Returns a dict of all DataFrames instead of a 7-tuple.
        Stages that are independent run in parallel for speed.
        """
        def progress(pct, msg):
            if progress_callback:
                progress_callback(pct, msg)
            logger.info("[%d%%] %s", pct, msg)

        progress(5, "Resolving host group...")
        group_id = self.resolve_group_id(group_name)

        progress(10, "Loading hosts and tags...")
        host_tags = self.fetch_hosts_and_tags(group_id)

        # Run independent stages in parallel
        progress(20, "Loading data in parallel (capacity, hardware, disks, databases, events)...")
        results = {}
        errors = {}

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {
                pool.submit(self.fetch_capacity_trends, group_id, days): "cap_df",
                pool.submit(self.fetch_hardware, group_id): "hw_df",
                pool.submit(self.fetch_disk_usage, group_id): "disk_df",
                pool.submit(self.fetch_db_trends, group_id, days): "db_df",
                pool.submit(self.fetch_problems_and_events, group_id, days): "problems",
            }
            try:
                for future in as_completed(futures, timeout=settings.fetch_stage_timeout_seconds):
                    key = futures[future]
                    try:
                        results[key] = future.result(timeout=30)
                        progress_pcts = {"cap_df": 40, "hw_df": 50, "disk_df": 60, "db_df": 70, "problems": 85}
                        progress(progress_pcts.get(key, 50), f"Loaded {key}")
                    except TimeoutError:
                        logger.error("Stage %s result retrieval timed out", key)
                        errors[key] = TimeoutError(f"{key} timed out")
                        if key == "problems":
                            results[key] = (pd.DataFrame(), pd.DataFrame())
                        else:
                            results[key] = pd.DataFrame()
                    except Exception as e:
                        logger.error("Failed to load %s: %s", key, e)
                        errors[key] = e
                        if key == "problems":
                            results[key] = (pd.DataFrame(), pd.DataFrame())
                        else:
                            results[key] = pd.DataFrame()
            except TimeoutError:
                # Some stages didn't complete within the stage timeout
                for future, key in futures.items():
                    if key not in results and key not in errors:
                        logger.error("Stage %s exceeded %ds stage timeout — skipping",
                                     key, settings.fetch_stage_timeout_seconds)
                        errors[key] = TimeoutError(f"{key} exceeded stage timeout")
                        if key == "problems":
                            results[key] = (pd.DataFrame(), pd.DataFrame())
                        else:
                            results[key] = pd.DataFrame()
                        future.cancel()

        if errors:
            if len(errors) == 5:
                raise ZabbixAPIError(f"All fetch stages failed: {list(errors.values())[0]}")
            logger.warning("Some stages had errors: %s (continuing with partial data)", list(errors.keys()))

        problems_df, events_df = results.get("problems", (pd.DataFrame(), pd.DataFrame()))

        progress(85, "Zabbix data loaded — processing...")
        return {
            "cap_df": results.get("cap_df", pd.DataFrame()),
            "problems_df": problems_df,
            "host_tags": host_tags,
            "db_df": results.get("db_df", pd.DataFrame()),
            "disk_df": results.get("disk_df", pd.DataFrame()),
            "hw_df": results.get("hw_df", pd.DataFrame()),
            "events_df": events_df,
        }
