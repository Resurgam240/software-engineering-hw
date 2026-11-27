"""Reservation transactions with snapshots and strict two-object state changes."""

from sqlalchemy import select

from campus_market.auth import require_role
from campus_market.errors import require
from campus_market.models import (
    ProductVersion, Reservation, ReservationSnapshot, SnapshotImage, VersionImage, now,
)
from campus_market.product_commands import touch
from campus_market.repository import (
    active_reservation, assert_consistent, product_for_update, reservation_for_update,
)
from campus_market.validation import check_versions, reason_text


def reserve(session, actor, data):
    """Return an existing same-buyer reservation before rejecting stale page tokens."""
    require_role(actor, "USER")
    product = product_for_update(session, data["product_id"])
    require(product.seller_id != actor.id, "OWN_PRODUCT", "不能预约自己的商品", 403)
    assert_consistent(session, product)
    active = active_reservation(session, product)
    if active is not None and active.buyer_id == actor.id:
        return "reservation", active.id, active.status, active.status
    require(product.status == "SALE", "UNAVAILABLE", "商品已被预约或不在售，请刷新")
    check_versions(product, data)
    require(data.get("content_version") == product.content_version,
            "STALE_CONTENT", "商品内容已变化，请重新查看")
    message = reason_text(data.get("message", ""), "message")
    version = session.get(ProductVersion, (product.id, product.content_version))
    reservation = Reservation(product_id=product.id, buyer_id=actor.id,
                              seller_id=product.seller_id, original_message=message)
    session.add(reservation)
    session.flush()
    session.add(ReservationSnapshot(
        reservation_id=reservation.id, product_id=product.id, content_version=product.content_version,
        title=version.title, category=version.category, condition=version.condition,
        price=version.price, description=version.description,
    ))
    session.flush()
    for link in session.scalars(select(VersionImage).where(
        VersionImage.product_id == product.id, VersionImage.version == product.content_version
    )):
        session.add(SnapshotImage(reservation_id=reservation.id,
                                  position=link.position, image_id=link.image_id))
    touch(product, "RESERVED")
    return "reservation", reservation.id, "", "PENDING"


def party_reservation(session, actor, data):
    """Lock and validate paired rows before applying any reservation command."""
    require_role(actor, "USER")
    product, reservation = reservation_for_update(session, data["reservation_id"])
    require(actor.id in (reservation.buyer_id, reservation.seller_id),
            "NOT_FOUND", "对象不存在或不可访问", 404)
    assert_consistent(session, product)
    check_versions(product, data, reservation)
    require(product.status == "RESERVED" and reservation.status in ("PENDING", "CONFIRMED"),
            "TERMINAL_STATE", "预约已结束或当前状态不允许此操作，请刷新")
    return product, reservation


def confirm(session, actor, data):
    """Only the seller may confirm an awaiting reservation."""
    product, reservation = party_reservation(session, actor, data)
    require(actor.id == reservation.seller_id, "FORBIDDEN", "仅卖家可确认预约", 403)
    require(reservation.status == "PENDING", "STATE", "只有待确认预约可以确认")
    reservation.status = "CONFIRMED"
    reservation.row_version += 1
    touch(product)
    return "reservation", reservation.id, "PENDING", "CONFIRMED"


def reject(session, actor, data):
    """Rejection releases the product, retaining the snapshot and original message."""
    product, reservation = party_reservation(session, actor, data)
    require(actor.id == reservation.seller_id, "FORBIDDEN", "仅卖家可拒绝预约", 403)
    require(reservation.status == "PENDING", "STATE", "只有待确认预约可以拒绝")
    reservation.reason = reason_text(data.get("reason", ""))
    reservation.status = "REJECTED"
    reservation.row_version += 1
    touch(product, "SALE")
    return "reservation", reservation.id, "PENDING", "REJECTED"


def cancel(session, actor, data):
    """Buyers may cancel either active state; sellers may cancel only CONFIRMED."""
    product, reservation = party_reservation(session, actor, data)
    require(actor.id == reservation.buyer_id or reservation.status == "CONFIRMED",
            "STATE", "卖家应拒绝待确认预约；只有已确认预约可由卖家取消")
    before = reservation.status
    reservation.reason = reason_text(data.get("reason", ""))
    reservation.cancel_actor_id = actor.id
    reservation.cancel_type = "VOLUNTARY"
    reservation.status = "CANCELLED"
    reservation.row_version += 1
    touch(product, "SALE")
    return "reservation", reservation.id, before, "CANCELLED"


def complete(session, actor, data):
    """Completion is a seller declaration, not proof of real payment or delivery."""
    product, reservation = party_reservation(session, actor, data)
    require(actor.id == reservation.seller_id, "FORBIDDEN", "仅卖家可标记完成", 403)
    require(reservation.status == "CONFIRMED", "STATE", "只有已确认预约可以标记完成")
    reservation.status = "COMPLETED"
    reservation.completed_at = now()
    reservation.row_version += 1
    touch(product, "SOLD")
    return "reservation", reservation.id, "CONFIRMED", "COMPLETED"
