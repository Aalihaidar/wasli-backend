#!/usr/bin/env bash
# =============================================================
#  scripts/entrypoint.prod.sh — production container entrypoint
#
#  1. Applies database migrations (skip with RUN_MIGRATIONS=false —
#     e.g. when a separate release job migrates, so
#     parallel instances don't race each other).
#  2. Starts the command (Gunicorn by default) as PID 1.
#
#  Gunicorn defaults, all overridable by the platform's environment:
#    PORT (8080) · WEB_CONCURRENCY (2 workers) · GUNICORN_CMD_ARGS
# =============================================================

set -euo pipefail

if [[ "${RUN_MIGRATIONS:-true}" == "true" ]]; then
    echo "▶ Applying database migrations…"
    python manage.py migrate --noinput
fi

if [[ "${1:-}" == "gunicorn" ]]; then
    # Explicit GUNICORN_CMD_ARGS wins; otherwise sensible container defaults.
    # Gunicorn's optional control socket needs a writable home directory, which the non-root
    # `app` user does not have; nothing uses it in a container, so it is switched off.
    #
    # The access log writes one line per request: the method and the path (%(U)s, never the
    # query string, which carries a customer's position on GET /restaurants/nearby), the
    # status, the size, the time in milliseconds and the request id the API sends back.
    ACCESS_LOG_FORMAT='%(h)s "%(m)s %(U)s" %(s)s %(b)s %(M)sms rid=%({x-request-id}o)s'
    DEFAULT_ARGS="--bind=0.0.0.0:${PORT:-8080} --threads=4 --timeout=120"
    DEFAULT_ARGS+=" --access-logfile=- --error-logfile=- --no-control-socket"
    DEFAULT_ARGS+=" --access-logformat='${ACCESS_LOG_FORMAT}'"
    export GUNICORN_CMD_ARGS="${GUNICORN_CMD_ARGS:-${DEFAULT_ARGS}}"
    echo "▶ Starting Gunicorn on :${PORT:-8080} (${WEB_CONCURRENCY:-2} workers)"
fi

exec "$@"
