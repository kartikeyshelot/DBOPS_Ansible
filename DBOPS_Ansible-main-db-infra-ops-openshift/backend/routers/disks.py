"""
GET /api/disks — Disk usage data.
"""

import logging
from fastapi import APIRouter
from typing import Optional
from sqlalchemy import text
from database import get_db, get_latest_fetch_id
from utils import get_filtered_server_names, scoped_query

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/disks")
def get_disks(
    server_name: Optional[str] = None,
    search: Optional[str] = None, priority: Optional[str] = None,
    environment: Optional[str] = None, app_code: Optional[str] = None,
):
    with get_db() as session:
        fetch_id = get_latest_fetch_id(session)
        if not fetch_id:
            return []

        if server_name:
            rows = session.execute(
                text("SELECT * FROM disks WHERE fetch_id = :fid AND server_name = :name"),
                {"fid": fetch_id, "name": server_name},
            ).mappings().fetchall()
        else:
            names = get_filtered_server_names(session, fetch_id, search, priority, environment, app_code)
            rows = scoped_query(session,
                "SELECT * FROM disks WHERE fetch_id = :fetch_id", fetch_id, names)

        return [dict(r) for r in rows]
