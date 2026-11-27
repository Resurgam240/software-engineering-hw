"""Relational domain model, immutable historical content, and audit metadata."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index,
    Integer, Numeric, String, Text, UniqueConstraint, Uuid, text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    """Identifiers are independent of mutable titles or usernames."""
    return str(uuid4())


def now() -> datetime:
    """All persisted instants originate from the server and use UTC."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Common SQLAlchemy registry; Alembic imports its metadata."""


class User(Base):
    """Buyer and seller are contextual roles of one ordinary account."""

    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('USER','ADMIN')"),)
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(20), unique=True)
    nickname: Mapped[str] = mapped_column(String(40), default="")
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(10), default="USER")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LoginSession(Base):
    """Only a digest of the opaque session secret is stored in the database."""

    __tablename__ = "login_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    csrf_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Product(Base):
    """Mutable state points to an immutable version of public content."""

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT','PENDING','REJECTED','SALE','RESERVED','OFF','VIOLATED','SOLD')"),
        CheckConstraint("row_version > 0 AND content_version > 0"),
        Index("ix_products_status_published", "status", "published_at"),
    )
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    seller_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(12), default="DRAFT")
    content_version: Mapped[int] = mapped_column(Integer, default=1)
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProductVersion(Base):
    """Historical versions are never updated, even during draft editing."""

    __tablename__ = "product_versions"
    __table_args__ = (CheckConstraint("price IS NULL OR (price >= 0.01 AND price <= 99999.99)"),)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(30))
    condition: Mapped[str | None] = mapped_column(String(30))
    price: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    description: Mapped[str] = mapped_column(Text, default="")


class ImageAsset(Base):
    """A UUID-named asset is written once and only served after authorization."""

    __tablename__ = "image_assets"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    storage_key: Mapped[str] = mapped_column(String(50), unique=True)
    mime: Mapped[str] = mapped_column(String(20))
    byte_size: Mapped[int] = mapped_column(Integer)


class VersionImage(Base):
    """Foreign keys keep version image references resolvable."""

    __tablename__ = "product_version_images"
    __table_args__ = (
        ForeignKeyConstraint(["product_id", "version"],
                             ["product_versions.product_id", "product_versions.version"]),
        UniqueConstraint("product_id", "version", "image_id"),
        CheckConstraint("position BETWEEN 1 AND 3"),
    )
    product_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_id: Mapped[str] = mapped_column(ForeignKey("image_assets.id"))


class ReviewBatch(Base):
    """Decisions are bound to a particular submitted content version."""

    __tablename__ = "review_batches"
    __table_args__ = (
        ForeignKeyConstraint(["product_id", "content_version"],
                             ["product_versions.product_id", "product_versions.version"]),
        CheckConstraint("status IN ('PENDING','WITHDRAWN','APPROVED','REJECTED')"),
        Index("uq_pending_review", "product_id", unique=True, postgresql_where=text("status = 'PENDING'")),
    )
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), index=True)
    content_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="PENDING")
    admin_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Reservation(Base):
    """Immutable message plus mutable state; one active reservation per product."""

    __tablename__ = "reservations"
    __table_args__ = (
        CheckConstraint("buyer_id <> seller_id"),
        CheckConstraint("status IN ('PENDING','CONFIRMED','CANCELLED','REJECTED','COMPLETED')"),
        CheckConstraint("(status = 'COMPLETED') = (completed_at IS NOT NULL)"),
        Index("uq_active_reservation", "product_id", unique=True,
              postgresql_where=text("status IN ('PENDING','CONFIRMED')")),
        Index("uq_completed_reservation", "product_id", unique=True,
              postgresql_where=text("status = 'COMPLETED'")),
    )
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    buyer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    seller_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(12), default="PENDING")
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    original_message: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(Text, default="")
    cancel_actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    cancel_type: Mapped[str | None] = mapped_column(String(20))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ReservationSnapshot(Base):
    """Public content at reservation time, independent of later product edits."""

    __tablename__ = "reservation_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(["product_id", "content_version"],
                             ["product_versions.product_id", "product_versions.version"]),
    )
    reservation_id: Mapped[str] = mapped_column(ForeignKey("reservations.id"), primary_key=True)
    product_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    content_version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(30))
    condition: Mapped[str] = mapped_column(String(30))
    price: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    description: Mapped[str] = mapped_column(Text)


class SnapshotImage(Base):
    """Historical image references share immutable assets with public versions."""

    __tablename__ = "snapshot_images"
    reservation_id: Mapped[str] = mapped_column(
        ForeignKey("reservation_snapshots.reservation_id"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_id: Mapped[str] = mapped_column(ForeignKey("image_assets.id"))


class OperationReceipt(Base):
    """No request text or private response is stored in a deduplication receipt."""

    __tablename__ = "operation_receipts"
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    operation_key: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    result_kind: Mapped[str] = mapped_column(String(20))
    result_id: Mapped[str] = mapped_column(String(36))
    result_code: Mapped[str] = mapped_column(String(30), default="OK")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OperationLog(Base):
    """Append-only metadata; logical target IDs survive permitted draft deletion."""

    __tablename__ = "operation_logs"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    actor_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), index=True)
    role_at_time: Mapped[str] = mapped_column(String(10))
    target_type: Mapped[str] = mapped_column(String(25))
    target_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(40), index=True)
    before_state: Mapped[str] = mapped_column(String(20), default="")
    after_state: Mapped[str] = mapped_column(String(20), default="")
    result: Mapped[str] = mapped_column(String(10))
    failure_code: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class PrivateAccessLog(Base):
    """Every administrative read commits its own reason before revealing text."""

    __tablename__ = "private_access_logs"
    __table_args__ = (CheckConstraint("purpose IN ('VIOLATION','STATE_CHECK') AND length(trim(reason)) > 0"),)
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    admin_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reservation_id: Mapped[str] = mapped_column(ForeignKey("reservations.id"))
    purpose: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ViolationRecord(Base):
    """A completed sale can receive a NOTE but never be reversed."""

    __tablename__ = "violation_records"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    admin_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(12))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
