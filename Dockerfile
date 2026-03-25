FROM python:3.12-slim AS base

# Install litestream for SQLite replication
ARG LITESTREAM_VERSION=0.3.13
ADD https://github.com/benbjohnson/litestream/releases/download/v${LITESTREAM_VERSION}/litestream-v${LITESTREAM_VERSION}-linux-amd64.tar.gz /tmp/litestream.tar.gz
RUN tar -C /usr/local/bin -xzf /tmp/litestream.tar.gz && rm /tmp/litestream.tar.gz

WORKDIR /app

# Install Python dependencies from pinned requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY pyproject.toml .
COPY mandarin/ mandarin/
COPY marketing/ marketing/
COPY schema.sql .
COPY learner_profile.json .
COPY data/ data/
COPY litestream.yml /etc/litestream.yml
COPY docker-entrypoint.sh /docker-entrypoint.sh

RUN pip install --no-cache-dir . && chmod +x /docker-entrypoint.sh

# Create non-root user (CIS Docker Benchmark 4.1)
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser \
    && mkdir -p /data && chown -R appuser:appuser /app /data

ENV DATA_DIR=/data
ENV IS_PRODUCTION=true
EXPOSE 8080

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health/live')" || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
