import uuid
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
    UniqueConstraint,
    func
)

from sqlalchemy.dialects.postgresql import UUID, JSONB, UUID as PG_UUID
from sqlmodel import Field, Relationship, SQLModel


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

    status: str = Field(sa_column=Column(String(16), nullable=False))  # active/expired/canceled
    valid_from: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    valid_until: datetime = Field(sa_column=Column(DateTime(timezone=True)))

    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    )

    user: "User" = Relationship(
        back_populates="subscriptions",
        sa_relationship_kwargs={"lazy": "selectin"},
    )
    plan: "Plan" = Relationship(
        back_populates="subscriptions",
        sa_relationship_kwargs={"lazy": "selectin"},
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
