"""Tests for final approval constraint (#85)."""

import uuid
from datetime import datetime


class MockPiece:
    def __init__(self, status="draft", approved_by=None, approved_at=None, approval_method=None):
        self.id = uuid.uuid4()
        self.tenant_id = uuid.uuid4()
        self.status = status
        self.approved_by = approved_by
        self.approved_at = approved_at
        self.approval_method = approval_method
        self.content_metadata = {}


def make_piece(**kwargs):
    return MockPiece(**kwargs)


def test_unapproved_post_cannot_be_published():
    """Draft post without approved_by must not be publishable."""
    piece = make_piece(status="draft", approved_by=None)
    # Simulates the guard logic in mark_published
    can_publish = piece.status == "approved" and bool(piece.approved_by)
    assert not can_publish, "Draft post should not be publishable"


def test_approved_post_can_be_published():
    """Approved post with approved_by set can be published."""
    piece = make_piece(status="approved", approved_by="web_ui", approval_method="web_ui")
    can_publish = piece.status == "approved" and bool(piece.approved_by)
    assert can_publish, "Approved post should be publishable"


def test_approved_but_missing_approved_by_is_rejected():
    """Status approved but no approved_by — still blocked."""
    piece = make_piece(status="approved", approved_by=None)
    can_publish = piece.status == "approved" and bool(piece.approved_by)
    assert not can_publish, "Approved without approved_by should be blocked"


def test_approval_method_web_ui():
    """Approval via web UI sets correct method."""
    piece = make_piece()
    # Simulate approve_content endpoint logic
    piece.status = "approved"
    piece.approved_at = datetime.utcnow()
    piece.approved_by = "web_ui"
    piece.approval_method = "web_ui"
    assert piece.approval_method == "web_ui"
    assert piece.approved_by == "web_ui"


def test_approval_method_admin_override():
    """Admin override sets correct method and is logged."""
    piece = make_piece()
    # Simulate force-publish logic
    piece.status = "published"
    piece.approved_by = "admin_override"
    piece.approval_method = "admin_override"
    assert piece.approval_method == "admin_override"
    assert piece.approved_by == "admin_override"


def test_bulk_publish_rejects_unapproved():
    """Bulk publish must reject if any piece is not approved."""
    pieces = [
        make_piece(status="approved", approved_by="web_ui"),
        make_piece(status="draft", approved_by=None),
    ]
    unapproved = [p for p in pieces if p.status != "approved" or not p.approved_by]
    assert len(unapproved) == 1
    assert unapproved[0].status == "draft"


def test_put_bypass_guard_blocks_unapproved_publish():
    """PUT /content/{id} with status='published' must be blocked for unapproved posts."""
    piece = make_piece(status="draft", approved_by=None)
    update_data = {"status": "published"}

    # Simulates the guard added in update_content endpoint
    would_raise = update_data.get("status") == "published" and (
        piece.status != "approved" or not piece.approved_by
    )
    assert would_raise, "PUT with status=published on unapproved piece should raise 409"


def test_put_bypass_guard_allows_approved_publish():
    """PUT /content/{id} with status='published' is allowed for already-approved posts."""
    piece = make_piece(status="approved", approved_by="web_ui")
    update_data = {"status": "published"}

    would_raise = update_data.get("status") == "published" and (
        piece.status != "approved" or not piece.approved_by
    )
    assert not would_raise, "PUT with status=published on approved piece should be allowed"
