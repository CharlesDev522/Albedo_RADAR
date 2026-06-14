"""SQLAlchemy ORM models for MinerWatch."""

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class MinerStatus(str, enum.Enum):
    ACTIVE = "active"
    DEREGISTERED = "deregistered"
    REPLACED = "replaced"


class EventType(str, enum.Enum):
    REGISTERED = "registered"
    DEREGISTERED = "deregistered"
    UID_CHANGED = "uid_changed"
    HOTKEY_CHANGED = "hotkey_changed"
    HOTKEY_TRANSFER = "hotkey_transfer"
    STAKE_CHANGED = "stake_changed"
    EMISSION_CHANGED = "emission_changed"
    RANK_CHANGED = "rank_changed"
    VALIDATOR_STAKE_CHANGED = "validator_stake_changed"
    COMMITMENT_REVEALED = "commitment_revealed"
    COMMITMENT_UPDATED = "commitment_updated"


class Miner(Base):
    """Current state of a miner/neuron on a subnet."""

    __tablename__ = "miners"
    __table_args__ = (
        UniqueConstraint("subnet", "uid", name="uq_miners_subnet_uid"),
        Index("ix_miners_hotkey", "hotkey"),
        Index("ix_miners_coldkey", "coldkey"),
        Index("ix_miners_subnet_status", "subnet", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[int] = mapped_column(Integer, nullable=False)
    hotkey: Mapped[str] = mapped_column(String(64), nullable=False)
    coldkey: Mapped[str] = mapped_column(String(64), nullable=False)
    subnet: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    registered_at_block: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    status: Mapped[MinerStatus] = mapped_column(
        Enum(MinerStatus, name="miner_status"), default=MinerStatus.ACTIVE
    )
    is_validator: Mapped[bool] = mapped_column(default=False)
    current_stake: Mapped[float] = mapped_column(Float, default=0.0)
    current_alpha_stake: Mapped[float] = mapped_column(Float, default=0.0)
    current_tao_stake: Mapped[float] = mapped_column(Float, default=0.0)
    current_emission: Mapped[float] = mapped_column(Float, default=0.0)
    current_incentive: Mapped[float] = mapped_column(Float, default=0.0)
    current_rank: Mapped[float] = mapped_column(Float, default=0.0)
    current_trust: Mapped[float] = mapped_column(Float, default=0.0)
    rank_position: Mapped[int | None] = mapped_column(Integer, nullable=True)

    emissions: Mapped[list["Emission"]] = relationship(back_populates="miner", cascade="all, delete-orphan")
    stakes: Mapped[list["Stake"]] = relationship(back_populates="miner", cascade="all, delete-orphan")
    rankings: Mapped[list["Ranking"]] = relationship(back_populates="miner", cascade="all, delete-orphan")
    events: Mapped[list["Event"]] = relationship(back_populates="miner", cascade="all, delete-orphan")
    commitment: Mapped["MinerCommitment | None"] = relationship(
        back_populates="miner", uselist=False, cascade="all, delete-orphan"
    )


class MinerCommitment(Base):
    """Latest v5 on-chain model commitment per miner hotkey."""

    __tablename__ = "miner_commitments"
    __table_args__ = (
        UniqueConstraint("subnet", "hotkey", name="uq_commitment_subnet_hotkey"),
        Index("ix_commitments_subnet_uid", "subnet", "uid"),
        Index("ix_commitments_subnet_block", "subnet", "commit_block"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    miner_id: Mapped[int | None] = mapped_column(
        ForeignKey("miners.id", ondelete="SET NULL"), nullable=True
    )
    subnet: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    uid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hotkey: Mapped[str] = mapped_column(String(64), nullable=False)
    coldkey: Mapped[str | None] = mapped_column(String(64), nullable=True)
    registered_at_block: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    commit_block: Mapped[int] = mapped_column(BigInteger, nullable=False)
    block_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reveal_string: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(8), default="v5")
    repo: Mapped[str] = mapped_column(String(512), nullable=False)
    digest: Mapped[str] = mapped_column(String(128), nullable=False)
    model_uri: Mapped[str] = mapped_column(String(640), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    commit_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    miner: Mapped["Miner | None"] = relationship(back_populates="commitment")


class CommitmentHistory(Base):
    """Historical v5 commitment reveals per hotkey."""

    __tablename__ = "commitment_history"
    __table_args__ = (
        UniqueConstraint("subnet", "hotkey", "commit_block", "payload_hash", name="uq_commitment_history"),
        Index("ix_commitment_history_subnet_ts", "subnet", "revealed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subnet: Mapped[int] = mapped_column(Integer, nullable=False)
    uid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hotkey: Mapped[str] = mapped_column(String(64), nullable=False)
    coldkey: Mapped[str | None] = mapped_column(String(64), nullable=True)
    commit_block: Mapped[int] = mapped_column(BigInteger, nullable=False)
    block_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reveal_string: Mapped[str] = mapped_column(Text, nullable=False)
    repo: Mapped[str] = mapped_column(String(512), nullable=False)
    digest: Mapped[str] = mapped_column(String(128), nullable=False)
    model_uri: Mapped[str] = mapped_column(String(640), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    commit_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    revealed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Emission(Base):
    """Time-series emission snapshots per miner."""

    __tablename__ = "emissions"
    __table_args__ = (Index("ix_emissions_miner_ts", "miner_id", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    miner_id: Mapped[int] = mapped_column(ForeignKey("miners.id", ondelete="CASCADE"), nullable=False)
    block: Mapped[int] = mapped_column(BigInteger, nullable=False)
    emission: Mapped[float] = mapped_column(Float, nullable=False)
    incentive: Mapped[float] = mapped_column(Float, default=0.0)
    dividends: Mapped[float] = mapped_column(Float, default=0.0)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    miner: Mapped["Miner"] = relationship(back_populates="emissions")


class Stake(Base):
    """Time-series stake snapshots per miner."""

    __tablename__ = "stakes"
    __table_args__ = (Index("ix_stakes_miner_ts", "miner_id", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    miner_id: Mapped[int] = mapped_column(ForeignKey("miners.id", ondelete="CASCADE"), nullable=False)
    stake: Mapped[float] = mapped_column(Float, nullable=False)
    alpha_stake: Mapped[float] = mapped_column(Float, default=0.0)
    tao_stake: Mapped[float] = mapped_column(Float, default=0.0)
    block: Mapped[int] = mapped_column(BigInteger, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    miner: Mapped["Miner"] = relationship(back_populates="stakes")


class Ranking(Base):
    """Time-series rank snapshots per miner."""

    __tablename__ = "rankings"
    __table_args__ = (Index("ix_rankings_miner_ts", "miner_id", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    miner_id: Mapped[int] = mapped_column(ForeignKey("miners.id", ondelete="CASCADE"), nullable=False)
    rank: Mapped[float] = mapped_column(Float, nullable=False)
    rank_position: Mapped[int] = mapped_column(Integer, nullable=False)
    trust: Mapped[float] = mapped_column(Float, default=0.0)
    block: Mapped[int] = mapped_column(BigInteger, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    miner: Mapped["Miner"] = relationship(back_populates="rankings")


class Event(Base):
    """Miner lifecycle and state-change events."""

    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_type_ts", "event_type", "timestamp"),
        Index("ix_events_subnet_ts", "subnet", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[EventType] = mapped_column(Enum(EventType, name="event_type"), nullable=False)
    miner_id: Mapped[int | None] = mapped_column(ForeignKey("miners.id", ondelete="SET NULL"), nullable=True)
    subnet: Mapped[int] = mapped_column(Integer, nullable=False)
    block: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    miner: Mapped["Miner | None"] = relationship(back_populates="events")


class HotkeyRecord(Base):
    """Historical hotkey tracking across UIDs and subnets."""

    __tablename__ = "hotkey_records"
    __table_args__ = (
        Index("ix_hotkey_records_hotkey", "hotkey"),
        Index("ix_hotkey_records_subnet", "subnet"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hotkey: Mapped[str] = mapped_column(String(64), nullable=False)
    coldkey: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subnet: Mapped[int] = mapped_column(Integer, nullable=False)
    uid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    uid_history: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)


class ColdkeyRecord(Base):
    """Coldkey ownership aggregation for wallet clustering."""

    __tablename__ = "coldkey_records"
    __table_args__ = (Index("ix_coldkey_records_coldkey", "coldkey"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coldkey: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    miner_count: Mapped[int] = mapped_column(Integer, default=0)
    validator_count: Mapped[int] = mapped_column(Integer, default=0)
    total_stake: Mapped[float] = mapped_column(Float, default=0.0)
    total_emission: Mapped[float] = mapped_column(Float, default=0.0)
    hotkeys: Mapped[list[str]] = mapped_column(JSONB, default=list)
    subnets: Mapped[list[int]] = mapped_column(JSONB, default=list)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SubnetSnapshot(Base):
    """Periodic metagraph snapshot metadata."""

    __tablename__ = "subnet_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subnet: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    block: Mapped[int] = mapped_column(BigInteger, nullable=False)
    neuron_count: Mapped[int] = mapped_column(Integer, default=0)
    total_stake: Mapped[float] = mapped_column(Float, default=0.0)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
