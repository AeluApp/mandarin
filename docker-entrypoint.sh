#!/bin/sh
set -e

mkdir -p /data

# If Litestream S3 bucket is configured, restore DB and run under replication
if [ -n "$LITESTREAM_S3_BUCKET" ]; then
    echo "Restoring database from Litestream replica..."
    litestream restore -if-db-not-exists -if-replica-exists -config /etc/litestream.yml /data/mandarin.db

    echo "Starting gunicorn under Litestream replication..."
    exec litestream replicate -config /etc/litestream.yml -exec \
        "gunicorn mandarin.web.wsgi:app --bind 0.0.0.0:8080 --preload --worker-class gevent --workers 2 --worker-connections 100 --timeout 120 --max-requests 1000 --max-requests-jitter 50"
else
    echo "Starting gunicorn (no replication)..."
    exec gunicorn mandarin.web.wsgi:app --bind 0.0.0.0:8080 --preload --worker-class gevent --workers 2 --worker-connections 100 --timeout 120 --max-requests 1000 --max-requests-jitter 50
fi
