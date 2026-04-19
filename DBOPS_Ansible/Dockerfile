# ══════════════════════════════════════════════════════════════════════════════
# DB Infrastructure OPS — Multi-stage Docker build for OpenShift
# ══════════════════════════════════════════════════════════════════════════════

# ── Stage 1: Build React frontend ─────────────────────────────────────────────
FROM node:20-alpine AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build


# ── Stage 2: Install Python dependencies ──────────────────────────────────────
FROM python:3.12-slim AS deps

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r /tmp/requirements.txt


# ── Stage 3: Final production image ───────────────────────────────────────────
FROM python:3.12-slim

# Security labels
LABEL maintainer="db-infra-ops" \
      io.openshift.tags="python,fastapi,monitoring" \
      io.openshift.expose-services="8090:http" \
      io.openshift.non-scalable="false"

# ── OpenShift arbitrary UID support ──────────────────────────────────────────
# OpenShift assigns a random UID at runtime but always uses GID 0 (root group).
# All files must be group-readable/writable so any UID in group 0 can operate.
RUN useradd -u 1001 -g 0 -d /app -s /sbin/nologin appuser && \
    chmod g=u /etc/passwd

# Install only runtime system deps (psycopg2-binary needs libpq at runtime)
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

# Copy pre-built Python packages from deps stage
COPY --from=deps /install /usr/local

# Copy application code
WORKDIR /app
COPY backend/ ./

# Copy pre-built frontend into static/ (FastAPI serves it)
COPY --from=frontend /build/dist ./static/

# ── Fix permissions for OpenShift ────────────────────────────────────────────
# Everything owned by appuser:root(0), group has same perms as owner
RUN chown -R 1001:0 /app && \
    chmod -R g=u /app && \
    # Ensure /tmp is writable (emptyDir will overlay this in k8s, but
    # this makes the image work standalone too)
    chmod 1777 /tmp

# Drop to non-root user
USER 1001

EXPOSE 8090

# ── Health check (used by Docker; OpenShift uses its own probes) ─────────────
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:8090/api/ping || exit 1

# ── Production entry point ───────────────────────────────────────────────────
# Gunicorn with Uvicorn workers:
#   - workers=2      : suitable for 0.5-1 CPU pods (2×CPU is the rule of thumb)
#   - timeout=120    : long enough for Zabbix fetch background tasks
#   - graceful-timeout=30 : clean shutdown on SIGTERM (OpenShift sends this)
#   - access-logfile  : structured access logs to stdout
CMD ["gunicorn", "main:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8090", \
     "--workers", "2", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
