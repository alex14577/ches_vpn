import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
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
    refer_id: Optional[str] = Field(default=None, sa_column=Column(String(128)))

    username: Optional[str] = Field(default=None, sa_column=Column(String(64)))

    subscription_token: str = Field(
        sa_column=Column(UUID(as_uuid=False), server_default=func.gen_random_uuid())        )

    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    )

    subscriptions: list["Subscription"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin",
        },
    )

    vpn_binding: Optional["VpnBinding"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"uselist": False, "lazy": "selectin"},
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

    bindings: list["VpnBinding"] = Relationship(
        back_populates="server",
        sa_relationship_kwargs={"lazy": "selectin"},
    )

class VpnBinding(SQLModel, table=True):
    __tablename__ = "vpn_bindings"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_vpn_bindings_user"),
        UniqueConstraint("client_uuid", name="uq_vpn_bindings_client_uuid"),
    )

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

    server_id: uuid.UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("vpn_servers.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        )
    )

    inbound_id: int = Field(sa_column=Column(Integer, nullable=False))
    client_uuid: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))

    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    )

    user: "User" = Relationship(
        back_populates="vpn_binding",
        sa_relationship_kwargs={"lazy": "selectin"},
    )
    server: "VpnServer" = Relationship(
        back_populates="bindings",
        sa_relationship_kwargs={"lazy": "selectin"},
    )
