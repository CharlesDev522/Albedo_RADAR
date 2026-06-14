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

        block = int(metagraph.block.item())
        neurons: list[NeuronSnapshot] = []

        n = int(metagraph.n.item())
        for i in range(n):
            uid = int(metagraph.uids[i].item())
            neuron = self._extract_neuron(metagraph, i, uid)
            neurons.append(neuron)

        total_stake = sum(n.stake for n in neurons)
        return MetagraphSnapshot(subnet=netuid, block=block, neurons=neurons, total_stake=total_stake)

    def _extract_neuron(self, metagraph: Any, index: int, uid: int) -> NeuronSnapshot:
        """Extract neuron fields from metagraph tensors."""
        hotkey = str(metagraph.hotkeys[index])
        coldkey = str(metagraph.coldkeys[index])

        stake = float(metagraph.S[index].item())
        alpha_stake = float(metagraph.AS[index].item()) if hasattr(metagraph, "AS") else 0.0
        tao_stake = float(metagraph.TS[index].item()) if hasattr(metagraph, "TS") else 0.0
        rank = float(metagraph.R[index].item())
        trust = float(metagraph.T[index].item())
        incentive = float(metagraph.I[index].item())
        emission = float(metagraph.E[index].item()) if hasattr(metagraph, "E") else 0.0
        dividends = float(metagraph.D[index].item()) if hasattr(metagraph, "D") else 0.0

        is_validator = False
        if hasattr(metagraph, "validator_permit"):
            is_validator = bool(metagraph.validator_permit[index].item())

        active = True
        if hasattr(metagraph, "active"):
            active = bool(metagraph.active[index].item())

        return NeuronSnapshot(
            uid=uid,
            hotkey=hotkey,
            coldkey=coldkey,
            stake=stake,
            alpha_stake=alpha_stake,
            tao_stake=tao_stake,
            rank=rank,
            trust=trust,
            incentive=incentive,
            emission=emission,
            dividends=dividends,
            is_validator=is_validator,
            active=active,
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
