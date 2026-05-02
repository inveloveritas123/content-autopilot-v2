# Migration Notes

## 024 — ZFB → ZKG Tenant Rename (2026-05-02)

### What changed
- Tenant "ZFB" renamed to "ZKG"
- New API key: `***REMOVED-TENANT-KEY-ZKG***`
- Old API key `***REMOVED-TENANT-KEY***` remains valid for 3-month transition (until 2026-08-01)
- Test voice data (source=test/dummy/dev) deleted from tenant_voice_profile, tenant_customer_context, tenant_audience_avatar
- `voice_profile_id` stripped from content_pieces.content_metadata (no longer references deleted profiles)

### How to run
Standard `alembic upgrade head` — applies automatically with other migrations.

### After migration
1. Update any integrations using `***REMOVED-TENANT-KEY***` to use `***REMOVED-TENANT-KEY-ZKG***`
2. Remove `api_key_secondary` via migration 025 after transition period (target: 2026-08-01)

### NC path migration (manual — owner: Robert)
- Old path: `/zukunftsbund/Kunden/zfb/`
- New path: `/content-autopilot/v2/Kunde/ZKG/`
- Action required before 2026-06-01: Coordinate with Robert before moving NC files
- Tracked: content-autopilot-v2 issue #81
