"""Tests for market data client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.market_client import build_market_overview, fetch_tao_price_usd


@pytest.mark.asyncio
async def test_fetch_tao_price_usd_coingecko():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"bittensor": {"usd": 220.5}}

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("app.integrations.market_client.httpx.AsyncClient", return_value=mock_client):
        usd, source, updated = await fetch_tao_price_usd()

    assert usd == 220.5
    assert source == "coingecko"
    assert updated is not None


@pytest.mark.asyncio
async def test_build_market_overview_combines_price_and_burn():
    with (
        patch(
            "app.integrations.market_client.fetch_tao_price_usd",
            return_value=(200.0, "coingecko", None),
        ),
        patch(
            "app.integrations.market_client.fetch_subnet_economics",
            return_value={
                "registration_burn_tao": 1.5,
                "alpha_price_tao": 0.03,
                "chain_block": 123,
            },
        ),
    ):
        data = await build_market_overview(97)

    assert data["subnet"] == 97
    assert data["tao_price_usd"] == 200.0
    assert data["registration_burn_tao"] == 1.5
    assert data["registration_burn_usd"] == 300.0
    assert data["alpha_price_tao"] == 0.03
    assert data["chain_block"] == 123
