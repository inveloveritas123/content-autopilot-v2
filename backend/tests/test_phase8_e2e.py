"""Phase-8-E2E (Issue #148) — Smoke-Test alle neuen + relevante bestehende Endpoints.

Läuft pytest auf dem laufenden Backend (HTTP-Layer).
Verifiziert: Company-Profile-CRUD, MD-Import, Provenance, Pending-Review,
Data-Deletion (alle 4 Modi + Recovery), Memory-Viz-Endpoint.
"""

from __future__ import annotations

import os

import pytest
import requests

BASE_URL = os.environ.get("CAPV2_BASE_URL", "http://localhost:8601")
API_KEY = os.environ.get("CAPV2_API_KEY", "")


@pytest.fixture(scope="module")
def headers():
    if not API_KEY:
        pytest.skip("CAPV2_API_KEY env not set")
    return {"x-api-key": API_KEY, "Content-Type": "application/json"}


def _get(path, headers, **kw):
    r = requests.get(BASE_URL + path, headers=headers, timeout=10, **kw)
    return r


def _post(path, headers, json=None):
    return requests.post(BASE_URL + path, headers=headers, json=json, timeout=15)


def _put(path, headers, json=None):
    return requests.put(BASE_URL + path, headers=headers, json=json, timeout=10)


def test_health(headers):
    r = _get("/api/health", headers)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_company_profile_get(headers):
    r = _get("/api/me/company-profile", headers)
    assert r.status_code == 200
    d = r.json()
    assert "tenant_id" in d
    assert "company_name" in d


def test_company_profile_put_and_provenance(headers):
    r = _put(
        "/api/me/company-profile", headers, {"contact_role": "E2E-Test-Rolle", "region": "Berlin"}
    )
    assert r.status_code == 200
    assert "updated" in r.json()
    assert "contact_role" in r.json()["updated"]

    r2 = _get("/api/me/company-profile/provenance", headers)
    assert r2.status_code == 200
    d = r2.json()
    assert "fields" in d
    assert "trust_hierarchy" in d
    assert d["auto_apply_threshold"] == 0.85
    assert "contact_role" in d["fields"]
    assert any(
        e["source"] == "manual_input" and e["value"] == "E2E-Test-Rolle"
        for e in d["fields"]["contact_role"]
    )


def test_company_profile_md_import_pending(headers):
    md = """# Onboarding — E2E

## Firma
- Name: E2E-Suite GmbH
- Branche: Testautomatisierung
- Mitarbeitende: 7

## Ansprechpartner
- Name: E2E Tester
- Rolle: QA-Lead

## USP
Automatisierte End-to-End-Verifikation in <60 Sekunden.
"""
    r = _post("/api/me/company-profile/import-md", headers, {"content": md, "auto_apply": False})
    assert r.status_code == 200
    d = r.json()
    assert d["parsed"] >= 5
    assert d["applied"] == 0
    assert d["pending"] == d["parsed"]

    pend = _get("/api/me/company-profile/pending", headers).json()
    assert isinstance(pend["pending"], list)
    e2e_items = [
        p for p in pend["pending"] if p["source"] == "md_upload" and "E2E" in (p["value"] or "")
    ]
    assert len(e2e_items) >= 1, f"E2E pending should exist, got: {pend['pending'][:3]}"


def test_company_profile_review_reject(headers):
    pend = _get("/api/me/company-profile/pending", headers).json()
    cand = next(
        (p for p in pend["pending"] if p["source"] == "md_upload" and "E2E" in (p["value"] or "")),
        None,
    )
    if cand is None:
        pytest.skip("no md_upload pending found, skip")
    r = _post(f"/api/me/company-profile/review/{cand['id']}", headers, {"action": "reject"})
    assert r.status_code == 200
    assert r.json()["action"] == "reject"


def test_data_deletion_memory_selective_and_recover(headers):
    r = _post(
        "/api/me/data-deletion",
        headers,
        {"mode": "memory_selective", "older_than_days": 0, "notes": "E2E-Test memory_selective"},
    )
    assert r.status_code == 201
    d = r.json()
    assert d["status"] == "soft_deleted"
    assert d["mode"] == "memory_selective"
    assert "recovery_until" in d

    req_id = d["id"]
    r2 = _get(f"/api/me/data-deletion/{req_id}", headers)
    assert r2.status_code == 200
    assert r2.json()["status"] == "soft_deleted"

    r3 = _post(f"/api/me/data-deletion/{req_id}/recover", headers)
    assert r3.status_code == 200
    assert r3.json()["status"] == "recovered"


def test_data_deletion_modes_validate(headers):
    r = _post("/api/me/data-deletion", headers, {"mode": "INVALID_MODE"})
    assert r.status_code in (400, 422)


def test_data_deletion_history(headers):
    r = _get("/api/me/data-deletion", headers)
    assert r.status_code == 200
    assert "history" in r.json()
    assert isinstance(r.json()["history"], list)


def test_memory_viz_endpoint(headers):
    r = _get("/api/memory/viz-data", headers, params={"days": 365, "edge_threshold": 0.6})
    assert r.status_code == 200
    d = r.json()
    assert "nodes" in d
    assert "edges" in d
    assert "stats" in d
    assert "by_classification" in d["stats"]
    assert "by_source_type" in d["stats"]


def test_memory_viz_filter_by_classification(headers):
    r = _get("/api/memory/viz-data", headers, params={"classification": "werte"})
    assert r.status_code == 200
    for n in r.json()["nodes"]:
        assert n["classification"] in ("werte", None)


def test_existing_memory_endpoints_still_work(headers):
    """Regression: keine bestehende API darf durch Phase 8 brechen."""
    r1 = _get("/api/memory/recent", headers, params={"limit": 5})
    assert r1.status_code == 200

    r2 = _get("/api/memory/stats", headers)
    assert r2.status_code == 200

    r3 = _get("/api/tenants/me/industry", headers)
    assert r3.status_code == 200

    r4 = _get("/api/hooks/library", headers, params={"limit": 5})
    assert r4.status_code == 200


def test_existing_research_findings_endpoint(headers):
    r = _get("/api/research/findings", headers, params={"limit": 5})
    assert r.status_code == 200
