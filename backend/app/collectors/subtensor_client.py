"""Subtensor RPC client wrapper for MinerWatch collectors."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from bittensor.core.async_subtensor import AsyncSubtensor
from bittensor.core.metagraph import async_metagraph

from app.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class NeuronSnapshot:
    """Normalized neuron state from metagraph at a given block."""

    uid: int
    hotkey: str
    coldkey: str
    registered_at_block: int | None
    stake: float
    alpha_stake: float
    tao_stake: float
    rank: float
    trust: float
    incentive: float
    emission: float
    dividends: float
    is_validator: bool
    active: bool


@dataclass
class MetagraphSnapshot:
    """Complete subnet metagraph snapshot."""

    subnet: int
    block: int
    neurons: list[NeuronSnapshot]
    total_stake: float


def _balance_to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if hasattr(value, "tao"):
        return float(value.tao)
    return float(value)


class SubtensorClient:
    """Thin async wrapper over Bittensor SDK for metagraph polling."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._subtensor: AsyncSubtensor | None = None

    async def connect(self) -> None:
        self._subtensor = AsyncSubtensor(network=self.settings.bittensor_network)
        await self._subtensor.__aenter__()
        logger.info("Connected to Bittensor network: %s", self.settings.bittensor_network)

    async def disconnect(self) -> None:
        if self._subtensor:
            await self._subtensor.__aexit__(None, None, None)
            self._subtensor = None

    async def get_current_block(self) -> int:
        assert self._subtensor is not None
        return await self._subtensor.get_current_block()

    async def get_subnet_snapshot(self, netuid: int | None = None) -> MetagraphSnapshot:
        """Fetch and normalize metagraph data for a subnet."""
        assert self._subtensor is not None
        netuid = netuid or self.settings.default_subnet

        metagraph = await async_metagraph(
            netuid=netuid,
            network=self.settings.bittensor_network,
            lite=True,
            subtensor=self._subtensor,
            mechid=self.settings.mechid,
        )
        await metagraph.sync(subtensor=self._subtensor)

        block = int(metagraph.block.item()) if hasattr(metagraph.block, "item") else int(metagraph.block)
        reg_blocks: list[int] = list(getattr(metagraph, "block_at_registration", []) or [])

        neurons: list[NeuronSnapshot] = []
        for i, neuron in enumerate(metagraph.neurons):
            if getattr(neuron, "is_null", False):
                continue
            reg_block = int(reg_blocks[i]) if i < len(reg_blocks) else None
            neurons.append(self._extract_neuron(neuron, reg_block))

        total_stake = sum(n.stake for n in neurons)
        return MetagraphSnapshot(subnet=netuid, block=block, neurons=neurons, total_stake=total_stake)

    def _extract_neuron(self, neuron: Any, registered_at_block: int | None) -> NeuronSnapshot:
        """Extract fields from a NeuronInfoLite / NeuronInfo object (SDK v10)."""
        stake = _balance_to_float(getattr(neuron, "total_stake", None) or getattr(neuron, "stake", 0))

        return NeuronSnapshot(
            uid=int(neuron.uid),
            hotkey=str(neuron.hotkey),
            coldkey=str(neuron.coldkey),
            registered_at_block=registered_at_block,
            stake=stake,
            alpha_stake=0.0,
            tao_stake=stake,
            rank=float(getattr(neuron, "rank", 0.0) or 0.0),
            trust=float(getattr(neuron, "validator_trust", 0.0) or 0.0),
            incentive=float(getattr(neuron, "incentive", 0.0) or 0.0),
            emission=float(getattr(neuron, "emission", 0.0) or 0.0),
            dividends=float(getattr(neuron, "dividends", 0.0) or 0.0),
            is_validator=bool(getattr(neuron, "validator_permit", False)),
            active=bool(getattr(neuron, "active", True)),
        )

    async def list_subnets(self) -> list[int]:
        """Return list of active subnet netuids."""
        assert self._subtensor is not None
        try:
            info_list = await self._subtensor.get_all_metagraphs_info()
            return [info.netuid for info in info_list if info.netuid > 0]
        except Exception:
            logger.warning("Could not fetch all subnets, using default", exc_info=True)
            return [self.settings.default_subnet]
