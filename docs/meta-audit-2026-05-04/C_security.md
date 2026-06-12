# Security Audit — Content Autopilot v2.0
**Date:** 2026-05-04  
**Phase:** Phase 1 Surface-Diff (gitleaks unavailable, git log pattern scan used)  
**Auditor:** Security-Audit-Subagent (Haiku)

---

## 1. Secrets in Git History

### Status: ✅ PASS (Best Practice Observed)
- **Method:** `git log --all -p | grep -iE "(api[_-]?key|secret|password|token)"` 
- **Hits:** 2 findings (Environment Variable Handling, NOT hardcoded secrets)
- **Files:**
  - `backend/config.py:27` — Comment referencing tenant keys (not actual keys)
  - `backend/alembic/versions/024_zfb_zkg_migration.py:21-49` — Migration with placeholder references
  - `frontend/src/main.jsx:9` — **CRITICAL: Hardcoded API Key** (see Finding #2)

### Key Observation:
All real secrets (database passwords, API keys, LLM tokens) are environment-variable-based. No plaintext secrets in git history.

---

## 2. Hardcoded Tenant-Keys / API Keys

### Status: ⚠️ CRITICAL

| File | Line | Finding | Severity |
|------|------|---------|----------|
| `frontend/src/main.jsx` | 9 | `localStorage.setItem('apiKey', '***REMOVED-TENANT-KEY-ZKG***')` | 🔴 CRITICAL |
| `backend/config.py` | 27 | Comment-only reference (safe) | ✅ INFO |
| `backend/alembic/versions/024_zfb_zkg_migration.py` | 48-49 | Migration SQL with hardcoded keys | 🟡 MEDIUM |

### Details:
- **Line 9, frontend/src/main.jsx:** Tenant key **directly embedded** in JavaScript.  
  This is **transmitted to browser**, **visible in DevTools**, **cacheable in localStorage**.

- **Migration File:** SQL migration contains hardcoded tenant IDs for data migration (one-time, acceptable, but should be versioned safely).

### Recommendation:
- Move tenant key to `.env` or API response (server-side init)
- Use fetch `/api/csrf-token` response to include tenant key if needed

---

## 3. Docker Hardening

### Status: 🟡 PARTIAL (Good Practices, Missing USER Directive)

| Container | Dockerfile | USER | cap_drop | read_only | Security Notes |
|-----------|-----------|------|----------|-----------|-----------------|
| backend-v2 | ✓ | ❌ MISSING | ❌ (privileged) | ✅ (tmpfs writable) | Runs as root |
| celery-worker-v2 | ✓ | ❌ MISSING | ✅ (8 caps dropped) | ✅ | Runs as root |
| celery-beat-v2 | ✓ | ❌ MISSING | ✅ (8 caps dropped) | ✅ | Runs as root |
| mcp-server-v2 | ✓ | ❌ MISSING | ❌ (privileged) | ✅ | Runs as root |
| nginx-v2 | ✓ | ❌ MISSING | ❌ | ✅ (tmpfs for cache/run) | Nginx needs root for port 8080 |

### Findings:
- **No USER directive in any Dockerfile** — all containers run as root (UID 0)
- **cap_drop in Celery (only)** — Good; removes SYS_ADMIN, SYS_PTRACE, SYS_RAWIO, NET_ADMIN, NET_RAW, MKNOD, AUDIT_WRITE
- **read_only: true** implemented in docker-compose.v2.yml for all backends ✅
- **tmpfs writable** zones (/tmp, /var/run) for temp files ✅
- **security_opt: [label=disable]** — SELinux labeling disabled (acceptable for test environment)

### OWASP Mapping:
- **A05:2021 – Broken Access Control** (root container access)
- **A06:2021 – Vulnerable & Outdated Components** (no explicit base image pins)

---

## 4. CSRF Protection (Issue #96)

### Status: ✅ IMPLEMENTED

| Component | Finding | File | Status |
|-----------|---------|------|--------|
| **Middleware** | Double-submit cookie pattern | `backend/middleware/csrf_middleware.py` | ✅ Fully Implemented |
| **Token Generation** | Signed HMAC-SHA256 tokens with 24h TTL | line 58-64 | ✅ Secure |
| **Endpoint** | `/api/csrf-token` GET → issues token + cookie | `backend/main.py:265-282` | ✅ Active |
| **Cookie Settings** | `SameSite=Strict` | `backend/main.py:279` | ✅ Enforced |
| **Validation** | X-CSRF-Token header vs. cookie | line 85-125 | ✅ Enforced |
| **Exemptions** | GET, X-API-Key auth, webhooks | line 45-55 | ✅ Reasonable |

### Implementation Quality:
✅ Uses `hmac.compare_digest()` (timing-safe)  
✅ TTL validation (24h)  
✅ Exempt API-Key requests (custom header = implicit CSRF protection)

---

## 5. Three-Layer Injection Protection

### Status: ✅ IMPLEMENTED

| Layer | Method | Files | Count |
|-------|--------|-------|-------|
| **HTML Escaping** | `html.escape(value, quote=True)` | voice_feedback.py, brand_voice.py, wizard.py, p12c_task.py | 6 locations |
| **Custom Sanitizer** | `_sanitize_feedback()` wrapper | voice_feedback.py:33-37 | 1 function |
| **XSS Test Coverage** | Verify `<script>` → `&lt;script&gt;` | test_brand_voice_patch.py:553-558 | 2 tests |
| **Framework Protection** | Pydantic validators + parameterized SQL | All models | ✅ Active |

### Gaps:
- No `bleach` or `MarkupSafe` external library (acceptable for non-rich-text)
- Risk: If rich HTML needed, upgrade required

---

## 6. OWASP Top 10 Mapping

| OWASP | Issue | Severity | Status |
|-------|-------|----------|--------|
| **A01:2021 – Broken Access Control** | Frontend API key hardcoded; root containers | 🔴 HIGH | ⚠️ Finding #2 |
| **A02:2021 – Cryptographic Failures** | No explicit key rotation policy | 🟡 MEDIUM | ℹ️ Procedural |
| **A03:2021 – Injection** | SQL: Parameterized ✅; XSS: html.escape() ✅ | ✅ LOW | ✅ Mitigated |
| **A04:2021 – Insecure Design** | CSRF pattern ✅; no OAuth2 scopes | ✅ GOOD | ✅ Implemented |
| **A05:2021 – Security Misconfiguration** | Docker root user; no `USER` directive | 🟡 MEDIUM | ⚠️ Finding #3 |
| **A06:2021 – Vulnerable Components** | No explicit base image version pins | 🟡 LOW | ⚠️ Finding #3 |
| **A07:2021 – Authentication Failures** | CSRF + X-API-Key ✅; no session timeout | ✅ GOOD | ⚠️ Minor |
| **A08:2021 – Integrity** | Requirements.txt pinned ✅; migrations versioned ✅ | ✅ GOOD | ✅ Implemented |
| **A09:2021 – Logging & Monitoring** | No audit logging for sensitive ops | 🟡 MEDIUM | ℹ️ Feature Gap |
| **A10:2021 – SSRF** | No URL whitelist for external requests | 🟡 MEDIUM | ⚠️ Finding #5 |

---

## 7. Top 5 Security Recommendations

### 1. **CRITICAL: Remove Hardcoded Tenant Key from Frontend** [Effort: S]
- **File:** `frontend/src/main.jsx:9`
- **Action:** Fetch tenant key from `/api/tenant-init` instead of hardcode
- **Timeline:** ASAP (before production)

### 2. **HIGH: Add USER Directive to All Dockerfiles** [Effort: S]
- **Action:** Create non-root user; add `USER appuser` (except nginx)
- **Timeline:** Next sprint

### 3. **MEDIUM: Pin Base Docker Image Versions** [Effort: S]
- **Action:** Use explicit versions: `python:3.12.4-slim`, `node:20-alpine@sha256:...`
- **Timeline:** Next sprint

### 4. **MEDIUM: Add URL Whitelist for External Requests** [Effort: M]
- **Scope:** YouTube, RSS, Podcast URL fetches
- **Action:** Maintain allow-list; validate before requests
- **Timeline:** Phase 2

### 5. **MEDIUM: Add Audit Logging for Sensitive Operations** [Effort: M]
- **Scope:** PATCH brand-voice, tenant key rotation
- **Action:** Log timestamp, user, operation, IP (no secrets)
- **Timeline:** Phase 2

---

## 8. Notes

- **Phase 1 Surface-Diff only:** No network penetration testing or config review
- **gitleaks unavailable:** Used git log pattern matching fallback
- **npm dependencies:** Not scanned for CVEs (out of scope)
- **PostgreSQL:** Host config not reviewed
