FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app

# Sprint 14 hardening: run as a non-root user. The base image has no
# unprivileged user by default (unlike node:*-slim, which ships one) — the
# image is built and dependencies installed as root (needed for `pip
# install` to write into the system site-packages), then execution drops to
# `appuser` before the app ever runs.
RUN pip install --no-cache-dir . \
    && useradd --no-create-home --uid 1000 appuser

USER appuser

EXPOSE 8000

# Uses the stdlib rather than adding curl/wget as a runtime dependency just
# for this — one extra installed package for a healthcheck isn't worth the
# image-size and CVE-surface cost. /health has no auth and no DB dependency
# (app/api/health.py), so this only proves the process is alive and serving
# HTTP, not that the database is reachable — a real production healthcheck
# would need a stricter readiness probe; see README's Production Gaps.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request as u,sys; sys.exit(0 if u.urlopen('http://localhost:8000/health', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
