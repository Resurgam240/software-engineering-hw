"""Object lookup, locking order, invariant checks, and public projections."""

from sqlalchemy import select

from campus_market.constants import ACTIVE
from campus_market.errors import require
from campus_market.models import (
    Product, ProductVersion, Reservation, ReservationSnapshot, ReviewBatch,
    SnapshotImage, VersionImage,
)
from campus_market.validation import identifier


def product_for_update(session, product_id: str) -> Product:
    """The product is always the first business row locked in a transaction."""
    product = session.scalar(select(Product).where(Product.id == identifier(product_id)).with_for_update())
    require(product is not None, "NOT_FOUND", "对象不存在或不可访问", 404)
    return product


def reservation_for_update(session, reservation_id: str) -> tuple[Product, Reservation]:
    """Read a stable parent ID, lock the parent, then lock the child reservation."""
    reservation_id = identifier(reservation_id)
    product_id = session.scalar(select(Reservation.product_id).where(Reservation.id == reservation_id))
    require(product_id is not None, "NOT_FOUND", "对象不存在或不可访问", 404)
    product = product_for_update(session, product_id)
    reservation = session.scalar(
        select(Reservation).where(Reservation.id == reservation_id).with_for_update()
    )
    return product, reservation


def active_reservation(session, product: Product) -> Reservation | None:
    """The unique partial index allows at most one result."""
    return session.scalar(select(Reservation).where(
        Reservation.product_id == product.id, Reservation.status.in_(ACTIVE)
    ))


def assert_consistent(session, product: Product):
    """Block writes if imported or manually corrupted rows violate domain invariants."""
    active = active_reservation(session, product)
    require((active is not None) == (product.status == "RESERVED"),
            "INCONSISTENT_STATE", "检测到关联状态异常，已阻止操作，请联系维护人员")
    if active:
        require(active.seller_id == product.seller_id,
                "INCONSISTENT_STATE", "商品与预约卖家不一致，已阻止操作")
    completed = session.scalar(select(Reservation).where(
        Reservation.product_id == product.id, Reservation.status == "COMPLETED"
    ))
    require((completed is not None) == (product.status == "SOLD"),
            "INCONSISTENT_STATE", "成交关联异常，已阻止操作")


def can_see_product(session, actor, product: Product) -> bool:
    """Parties retain detail access through history after a product leaves public sale."""
    if product.status == "SALE":
        return True
    if actor is None:
        return False
    if actor.id == product.seller_id:
        return True
    if actor.role == "ADMIN":
        return product.status != "DRAFT"
    if product.status not in ("RESERVED", "SOLD"):
        return False
    return session.scalar(select(Reservation.id).join(
        ReservationSnapshot, ReservationSnapshot.reservation_id == Reservation.id
    ).where(Reservation.product_id == product.id, Reservation.buyer_id == actor.id,
            Reservation.status.in_(("PENDING", "CONFIRMED", "COMPLETED")),
            ReservationSnapshot.content_version == product.content_version).limit(1)) is not None


def product_view(session, product: Product) -> dict:
    """Expose current public fields with concurrency tokens and review information."""
    version = session.get(ProductVersion, (product.id, product.content_version))
    images = session.scalars(select(VersionImage.image_id).where(
        VersionImage.product_id == product.id, VersionImage.version == product.content_version
    ).order_by(VersionImage.position)).all()
    batch = session.scalar(select(ReviewBatch).where(ReviewBatch.product_id == product.id)
                           .order_by(ReviewBatch.created_at.desc()).limit(1))
    active = active_reservation(session, product)
    return {
        "id": product.id, "seller_id": product.seller_id, "status": product.status,
        "row_version": product.row_version, "content_version": product.content_version,
        "published_at": product.published_at, "title": version.title,
        "category": version.category, "condition": version.condition,
        "price": str(version.price) if version.price is not None else None,
        "description": version.description, "image_ids": list(images),
        "review_batch_id": batch.id if batch else None,
        "review_reason": batch.reason if batch else "",
        "active_reservation_id": active.id if active else None,
    }


def reservation_view(session, reservation: Reservation, actor, *, detail: bool = False) -> dict:
    """Lists omit messages; administrative detail also requires a separate audited read."""
    require(actor is not None and (actor.role == "ADMIN" or actor.id in
                                  (reservation.buyer_id, reservation.seller_id)),
            "NOT_FOUND", "对象不存在或不可访问", 404)
    snapshot = session.get(ReservationSnapshot, reservation.id)
    product = session.get(Product, reservation.product_id)
    result = {
        "id": reservation.id, "product_id": reservation.product_id,
        "buyer_id": reservation.buyer_id, "seller_id": reservation.seller_id,
        "status": reservation.status, "row_version": reservation.row_version,
        "product_row_version": product.row_version, "product_status": product.status,
        "reason": reservation.reason, "cancel_type": reservation.cancel_type,
        "completed_at": reservation.completed_at, "created_at": reservation.created_at,
        "snapshot": {"title": snapshot.title, "category": snapshot.category,
                     "condition": snapshot.condition, "price": str(snapshot.price),
                     "description": snapshot.description, "content_version": snapshot.content_version},
        "notice": "完成状态由卖家声明；按预约时标价统计，未核验实际付款或交付。",
    }
    if detail:
        result["snapshot"]["image_ids"] = list(session.scalars(select(SnapshotImage.image_id)
            .where(SnapshotImage.reservation_id == reservation.id).order_by(SnapshotImage.position)))
        if actor.id in (reservation.buyer_id, reservation.seller_id):
            result["original_message"] = reservation.original_message
    return result
