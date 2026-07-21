"""Tests for GitHub repo watch parsing and commit formatting."""

from datetime import datetime, timezone

from app.integrations.github_client import (
    GithubCommit,
    parse_github_watch_spec,
    parse_github_watch_specs,
    _parse_commit,
)
from app.notifications.github_slack import format_github_commit_alert, format_slack_body


def test_parse_github_watch_url():
    target = parse_github_watch_spec("https://github.com/tony-dendrite/albedo/tree/dev")
    assert target.owner == "tony-dendrite"
    assert target.repo == "albedo"
    assert target.branch == "dev"
    assert target.tree_url == "https://github.com/tony-dendrite/albedo/tree/dev"


def test_parse_github_watch_short_spec():
    target = parse_github_watch_spec("tony-dendrite/albedo@dev")
    assert target.full_name == "tony-dendrite/albedo"
    assert target.branch == "dev"


def test_parse_github_watch_specs_dedupes():
    targets = parse_github_watch_specs(
        [
            "tony-dendrite/albedo@dev",
            "https://github.com/tony-dendrite/albedo/tree/dev",
        ]
    )
    assert len(targets) == 1


def test_parse_commit_splits_subject_and_body():
    commit = _parse_commit(
        {
            "sha": "abc123def456",
            "html_url": "https://github.com/tony-dendrite/albedo/commit/abc123def456",
            "commit": {
                "message": "Fix reward math\n\nHandle edge case for crown margin.",
                "author": {"name": "Tony", "date": "2026-07-06T08:00:00Z"},
            },
        }
    )
    assert commit.subject == "Fix reward math"
    assert "edge case" in commit.body
    assert commit.short_sha == "abc123d"
    assert commit.author_name == "Tony"


def test_format_github_commit_alert():
    from app.integrations.github_client import GithubWatchTarget

    target = GithubWatchTarget("tony-dendrite", "albedo", "dev")
    commit = GithubCommit(
        sha="abc123",
        short_sha="abc123",
        subject="Update duel judge config",
        body="Short note about judges.",
        author_name="Tony",
        committed_at=datetime(2026, 7, 6, tzinfo=timezone.utc),
        html_url="https://github.com/tony-dendrite/albedo/commit/abc123",
    )
    title, message, detail = format_github_commit_alert(target, commit)
    assert "albedo@dev" in title
    assert message == "Update duel judge config"
    assert detail["commit_url"].endswith("/abc123")
    body = format_slack_body(target, commit)
    assert "Update duel judge config" in body
    assert "open on GitHub" in body
