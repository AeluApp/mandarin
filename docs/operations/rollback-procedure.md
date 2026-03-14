# Rollback Procedure

## Code Rollback (Fly.io)

### Roll back to previous release

```bash
# List recent deployments
fly releases

# Roll back to the previous image
fly deploy --image <registry>/<app>:<previous-version>
```

### Emergency: roll back immediately

```bash
# Fly.io keeps the last N images — deploy the previous one
fly releases
fly deploy --image registry.fly.io/<app-name>:deployment-<id>
```

## Data Rollback (Litestream → S3)

Litestream continuously replicates the SQLite database to S3. To restore from a point in time:

### 1. Stop the running instance

```bash
fly scale count 0
```

### 2. Restore from S3

```bash
# On a machine with AWS credentials and litestream installed:
litestream restore -o /tmp/mandarin-restored.db \
  -replica s3 \
  s3://${LITESTREAM_S3_BUCKET}/${LITESTREAM_S3_PATH:-mandarin}
```

### 3. Point-in-time restore

Litestream supports restoring to a specific timestamp:

```bash
litestream restore -o /tmp/mandarin-restored.db \
  -timestamp "2025-01-15T12:00:00Z" \
  -replica s3 \
  s3://${LITESTREAM_S3_BUCKET}/${LITESTREAM_S3_PATH:-mandarin}
```

### 4. Verify and redeploy

```bash
# Inspect the restored database
sqlite3 /tmp/mandarin-restored.db "SELECT * FROM schema_version;"

# Upload restored DB to the volume
fly ssh console -C "rm /data/mandarin.db"
fly ssh sftp shell
# put /tmp/mandarin-restored.db /data/mandarin.db

# Restart with restored data
fly scale count 1
```

## Migration Rollback

Migrations are **forward-only** — there are no down migrations. If a migration causes issues:

1. **Code rollback** will not undo schema changes (the old code must tolerate the new schema)
2. **Data rollback** via Litestream restore will revert both schema and data
3. All migrations are idempotent (`CREATE TABLE IF NOT EXISTS`, `INSERT OR IGNORE`)

### Safe migration practices

- Test migrations locally before deploying
- Migrations that add columns or tables are safe (backward compatible)
- Migrations that rename or drop columns require coordinated deploy:
  1. Deploy code that handles both old and new schema
  2. Run migration
  3. Deploy code that only handles new schema

## Monitoring After Rollback

```bash
# Check app health
fly status
curl https://<app-name>.fly.dev/api/health/ready

# Check logs for migration errors
fly logs | grep -i "migration\|schema\|error"

# Verify database integrity
fly ssh console -C "sqlite3 /data/mandarin.db 'PRAGMA integrity_check;'"
```

## Contacts

- **On-call**: Check Fly.io dashboard for instance status
- **Sentry**: Check error monitoring for new exceptions post-rollback
- **Litestream replication lag**: Check S3 bucket for latest WAL segment timestamp
