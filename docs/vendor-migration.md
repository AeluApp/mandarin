# Vendor Migration Path

How to export all data from the Aelu learning system for migration to another platform or for GDPR compliance.

## Export Endpoints

### 1. GDPR Data Export (JSON)

```
GET /api/account/export
Authorization: Bearer <token>
```

Returns a complete JSON archive of all personal data: user profile, progress records, session logs, error history, vocabulary encounters, and context notes. All timestamps are ISO 8601 UTC. Suitable for GDPR Article 20 (data portability) requests.

### 2. xAPI Statement Export

```
GET /api/xapi/statements
GET /api/xapi/statements?since=2026-01-01T00:00:00Z
Authorization: Bearer <token>
```

Returns learning activity as xAPI (IEEE 9274.1.1 Experience API) statements. Compatible with any Learning Record Store (LRS) such as Learning Locker, SCORM Cloud, or Watershed. Supports date filtering via `since` parameter.

### 3. Caliper Event Export

```
GET /api/caliper/events
GET /api/caliper/events?since=2026-01-01T00:00:00Z
Authorization: Bearer <token>
```

Returns learning events in IMS Caliper Analytics 1.2 format. Compatible with IMS-certified analytics platforms. Includes session events, assessment events, and navigation events.

### 4. Common Cartridge Export

```
GET /api/export/common-cartridge
GET /api/export/common-cartridge?level=2
Authorization: Bearer <token>
```

Downloads an IMS Common Cartridge 1.3 package (.imscc) containing vocabulary items and QTI 2.1 assessments. Filter by HSK level with the `level` parameter. Importable into Canvas, Blackboard, Moodle, and other CC-compatible LMS platforms.

### 5. CSV Exports

```
GET /api/export/progress      # Vocabulary progress: item, mastery, reviews, last_seen
GET /api/export/sessions       # Session history: date, duration, drills, score
GET /api/export/errors         # Error log: item, error_type, context, timestamp
Authorization: Bearer <token>
```

Standard CSV format with headers. Compatible with Excel, Google Sheets, pandas, R, or any analytics tool.

## Reference Documentation

### Data Dictionary

See `docs/data-dictionary.md` for complete documentation of all 16 database tables including:
- Column names, types, and constraints
- PII classification per column
- Retention policies
- Foreign key relationships

### OpenAPI Specification

See `docs/openapi.yaml` for the full API specification. Use it to:
- Generate client libraries in any language (`openapi-generator`)
- Build automated migration scripts
- Validate API responses during migration

## Migration Checklist

1. **Export user data**: `GET /api/account/export` for complete personal data archive
2. **Export learning records**: Choose xAPI or Caliper format based on target platform
3. **Export content**: `GET /api/export/common-cartridge` for vocabulary and assessments
4. **Export analytics**: Download CSV exports for historical analysis
5. **Verify completeness**: Cross-reference row counts with the data dictionary
6. **Delete account**: `DELETE /api/account` to remove all data (GDPR Article 17)
