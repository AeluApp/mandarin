#!/bin/sh
set -e

mkdir -p /data

# If Litestream replica URL is configured, restore DB and run under replication
if [ -n "$LITESTREAM_REPLICA_URL" ]; then
    echo "Restoring database from Litestream replica..."
    litestream restore -if-db-not-exists -if-replica-exists -config /etc/litestream.yml /data/mandarin.db

    echo "Starting gunicorn under Litestream replication..."
    exec litestream replicate -config /etc/litestream.yml -exec \
        "gunicorn mandarin.web.wsgi:app --bind 0.0.0.0:8080 --worker-class gevent --workers 2 --worker-connections 100 --timeout 120 --max-requests 1000 --max-requests-jitter 50"
else
    echo "Starting gunicorn (no replication)..."
    exec gunicorn mandarin.web.wsgi:app --bind 0.0.0.0:8080 --worker-class gevent --workers 2 --worker-connections 100 --timeout 120 --max-requests 1000 --max-requests-jitter 50
fi
