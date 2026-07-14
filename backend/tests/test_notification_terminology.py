"""Tests for notification terminology helpers."""

from app.notifications.terminology import prose_for, title_for


def test_slot_title_uses_publish_not_buy():
    title = title_for("slot_new", 97, {"uid": 42, "commitment_type": "v7"})
    assert "published v7 commitment" in title
    assert "bought" not in title.lower()


def test_commit_updated_title():
    title = title_for(
        "commit_updated",
        97,
        {"uid": 166, "repo": "ns/model"},
    )
    assert "changed CommitmentOf" in title
