import uuid
import enum
from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func
)

from sqlalchemy.dialects.postgresql import UUID, ENUM, JSONB, UUID as PG_UUID
from sqlmodel import Field, Relationship, SQLModel
from sqlalchemy.orm import DeclarativeBase


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )

    tg_user_id: int = Field(
        sa_column=Column(BigInteger, unique=True, nullable=False, index=True)
    )

    # NEW: "yndx" или token пригласившего пользователя (first-touch)
    refer_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String(128), index=True),
    )

    username: Optional[str] = Field(default=None, sa_column=Column(String(64)))

    subscription_token: str = Field(
        sa_column=Column(UUID(as_uuid=False), server_default=func.gen_random_uuid()))

    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), 
                         server_default=func.now(), 
                         nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), 
                         server_default=func.now(), 
                         onupdate=func.now(), 
                         nullable=False))

    subscriptions: list["Subscription"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin",
        },
    )


class Plan(SQLModel, table=True):
    __tablename__ = "plans"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )

    code: str = Field(sa_column=Column(String(32), unique=True, nullable=False, index=True))
    title: str = Field(sa_column=Column(String(128), nullable=False))
    description: str = Field(sa_column=Column(Text, nullable=False))

    price_rub: int = Field(sa_column=Column(Integer, nullable=False))
    duration_days: Optional[int] = Field(default=None, sa_column=Column(Integer, nullable=True))

    # ✅ ВАЖНО: явный Boolean, иначе будет NullType()
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true"),
    )

    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    )

    subscriptions: list["Subscription"] = Relationship(
        back_populates="plan",
        sa_relationship_kwargs={"lazy": "selectin"},
    )

class SubscriptionStatus(str, enum.Enum):
    pending_payment = "pending_payment"
    active = "active"
    payment_failed = "payment_failed"
    canceled = "canceled"
    expired = "expired"

pg_status_enum = ENUM(
    SubscriptionStatus,
    name="subscription_status",
    create_type=True,
)

class Subscription(SQLModel, table=True):
    __tablename__ = "subscriptions"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )

    user_id: uuid.UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )

    plan_id: uuid.UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("plans.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        )
    )
    
    expected_amount_minor: int = Field(sa_column=Column(Integer, nullable=False))

    status: SubscriptionStatus = Field(sa_column=Column(pg_status_enum, nullable=False))  # pending_payment/active/payment_failed/canceled/expired
    valid_from: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    valid_until: datetime = Field(sa_column=Column(DateTime(timezone=True)))

    matched_event_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("payment_events.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )

    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    )

    user: "User" = Relationship(back_populates="subscriptions", sa_relationship_kwargs={"lazy": "selectin"})
    plan: "Plan" = Relationship(back_populates="subscriptions", sa_relationship_kwargs={"lazy": "selectin"})

class Base(DeclarativeBase):
    pass

class PaymentEvent(SQLModel, table=True):
    __tablename__ = "payment_events"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )

    source: str = Field(sa_column=Column(String(32), nullable=False))  # vk / email / sms / ...
    received_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, index=True))

    # store text + metadata (peer_id, sender_id, message_id, etc.)
    payload: dict = Field(sa_column=Column(JSONB, nullable=False))

    # amount in minor units (kopeks/cents)
    amount_minor: int = Field(sa_column=Column(Integer, nullable=False))

    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    )

    def __repr__(self) -> str:
        return (
            f"PaymentEvent(id={self.id}, source={self.source!r}, received_at={self.received_at!r}, "
            f"amount_minor={self.amount_minor})"
        )

class VpnServer(SQLModel, table=True):
    __tablename__ = "vpn_servers"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )

    code: str = Field(sa_column=Column(String(32), unique=True, nullable=False, index=True))
    api_base_url: str = Field(sa_column=Column(String(512), nullable=False))
    api_username: str = Field(sa_column=Column(String(128), nullable=False))
    api_password: str = Field(sa_column=Column(String(128), nullable=False))

    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    )


class UserTrafficSnapshot(SQLModel, table=True):
    __tablename__ = "user_traffic_snapshots"

    day: date = Field(
        sa_column=Column(Date, primary_key=True, nullable=False)
    )
    user_id: uuid.UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        )
    )
    total_bytes: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False),
    )
    daily_bytes: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class DailyUsageStat(SQLModel, table=True):
    __tablename__ = "daily_usage_stats"

    day: date = Field(
        sa_column=Column(Date, primary_key=True, nullable=False)
    )
    active_users: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False),
    )
    total_bytes: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
