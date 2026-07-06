"""Tests for Albedo dashboard HTTP client."""

from unittest.mock import AsyncMock, patch

import pytest

from app.integrations import albedo_dashboard as dash


@pytest.mark.asyncio
async def test_fetch_dashboard_fresh_bypasses_cache():
    dash._CACHE.clear()
    payload_a = {"updated_at": "a", "eval_runs": []}
    payload_b = {"updated_at": "b", "eval_runs": [{"eval_run_id": "x"}]}

    with patch("httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client_cls.return_value.__aenter__.return_value = client
        client.get = AsyncMock(
            side_effect=[
                _mock_response(payload_a),
                _mock_response(payload_b),
            ]
        )

        first = await dash.fetch_dashboard(fresh=True)
        second = await dash.fetch_dashboard(fresh=True)

    assert first["updated_at"] == "a"
    assert second["updated_at"] == "b"
    assert client.get.await_count == 2


def _mock_response(payload: dict):
    resp = AsyncMock()
    resp.raise_for_status = lambda: None
    resp.json = lambda: payload
    return resp
