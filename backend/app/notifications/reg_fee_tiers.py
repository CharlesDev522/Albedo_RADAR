"""Registration burn tier alerts — multiple thresholds per cycle."""

from __future__ import annotations

# Slack emoji per tier (descending burn = more urgent).
REG_FEE_TIER_EMOJI: dict[float, str] = {
    1.0: ":large_yellow_circle:",
    0.75: ":money_with_wings:",
    0.6: ":fire:",
}

DEFAULT_REG_FEE_THRESHOLDS_TAO: tuple[float, ...] = (0.55,)


def normalize_reg_fee_thresholds(raw: object) -> list[float]:
    """Parse and sort thresholds high → low (unique)."""
    if raw is None:
        values = list(DEFAULT_REG_FEE_THRESHOLDS_TAO)
    elif isinstance(raw, str):
        values = [float(p.strip()) for p in raw.split(",") if p.strip()]
    elif isinstance(raw, (list, tuple)):
        values = [float(x) for x in raw]
    else:
        values = [float(raw)]
    return sorted({round(v, 6) for v in values if v > 0}, reverse=True)


def reg_fee_tier_emoji(threshold: float) -> str:
    if threshold in REG_FEE_TIER_EMOJI:
        return REG_FEE_TIER_EMOJI[threshold]
    if threshold >= 1.0:
        return ":large_yellow_circle:"
    if threshold >= 0.75:
        return ":money_with_wings:"
    if threshold >= 0.6:
        return ":fire:"
    return ":rotating_light:"


def tiers_newly_crossed(
    burn: float,
    thresholds: list[float],
    already_alerted: set[float],
) -> list[float]:
    """Tiers crossed below that have not alerted yet this cycle (high → low)."""
    return [t for t in thresholds if burn < t and t not in already_alerted]


def tiers_to_seed_at_bootstrap(burn: float, thresholds: list[float]) -> set[float]:
    """Mark tiers already below burn at startup (no retroactive Slack)."""
    return {t for t in thresholds if burn < t}
