#!/bin/sh
set -e

mkdir -p /data

# If arguments are provided (e.g. release_command "mandarin seed"), run them directly.
# This is the standard Docker entrypoint pattern so that Fly release commands work.
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

# If Litestream S3 bucket is configured, restore DB and run under replication
if [ -n "$LITESTREAM_S3_BUCKET" ]; then
    echo "Restoring database from Litestream replica..."
    # -if-db-not-exists: skip if DB already exists (e.g. volume survives restart)
    # -if-replica-exists: skip if bucket is empty (first deploy before any backup)
    # || true: belt-and-suspenders — a restore failure must not prevent startup
    litestream restore -if-db-not-exists -if-replica-exists -config /etc/litestream.yml /data/mandarin.db || true

    echo "Starting gunicorn under Litestream replication..."
    exec litestream replicate -config /etc/litestream.yml -exec \
        "gunicorn mandarin.web.wsgi:app --bind 0.0.0.0:8080 --worker-class gevent --workers 2 --worker-connections 100 --timeout 120 --max-requests 1000 --max-requests-jitter 50"
else
    echo "Starting gunicorn (no replication)..."
    exec gunicorn mandarin.web.wsgi:app --bind 0.0.0.0:8080 --worker-class gevent --workers 2 --worker-connections 100 --timeout 120 --max-requests 1000 --max-requests-jitter 50
fi
