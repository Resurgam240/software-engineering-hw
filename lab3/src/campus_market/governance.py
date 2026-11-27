"""Administrative review and violation rules share the same transaction boundary."""

from sqlalchemy import select

from campus_market.auth import require_role
from campus_market.errors import require
from campus_market.models import ReviewBatch, ViolationRecord, now
from campus_market.product_commands import touch
from campus_market.repository import active_reservation, assert_consistent, product_for_update
from campus_market.validation import check_versions, reason_text


def review(session, actor, data):
    """Old batches and old content cannot authorize publication of a newer version."""
    require_role(actor, "ADMIN")
    product = product_for_update(session, data["product_id"])
    require(product.status != "DRAFT", "NOT_FOUND", "对象不存在或不可访问", 404)
    assert_consistent(session, product)
    check_versions(product, data)
    require(product.status == "PENDING", "STATE", "商品不处于待审核状态")
    batch = session.scalar(select(ReviewBatch).where(
        ReviewBatch.product_id == product.id, ReviewBatch.status == "PENDING"
    ))
    require(batch is not None and batch.id == data.get("batch_id")
            and batch.content_version == data.get("content_version"),
            "STALE_BATCH", "审核批次或内容已变化，请刷新")
    approve = data.get("decision") == "APPROVE"
    require(data.get("decision") in ("APPROVE", "REJECT"), "DECISION", "请选择审核结果", 422)
    batch.reason = "" if approve else reason_text(data.get("reason", ""))
    batch.admin_id = actor.id
    batch.status = "APPROVED" if approve else "REJECTED"
    touch(product, "SALE" if approve else "REJECTED")
    if approve:
        product.published_at = now()
    return "product", product.id, "PENDING", product.status


def violation(session, actor, data):
    """Atomic takedown terminates an active reservation without reopening the sale."""
    require_role(actor, "ADMIN")
    product = product_for_update(session, data["product_id"])
    require(product.status != "DRAFT", "NOT_FOUND", "对象不存在或不可访问", 404)
    assert_consistent(session, product)
    check_versions(product, data)
    reason = reason_text(data.get("reason", ""))
    before = product.status
    require(before in ("PENDING", "SALE", "RESERVED", "OFF", "SOLD"),
            "STATE", "当前状态不能进行新的违规处理")
    action = "NOTE"
    if before == "PENDING":
        batch = session.scalar(select(ReviewBatch).where(
            ReviewBatch.product_id == product.id, ReviewBatch.status == "PENDING"
        ))
        require(batch is not None and batch.id == data.get("batch_id")
                and batch.content_version == data.get("content_version"),
                "STALE_BATCH", "审核批次已变化")
        batch.status, batch.admin_id, batch.reason = "REJECTED", actor.id, reason
        touch(product, "REJECTED")
        action = "REJECT"
    elif before != "SOLD":
        reservation = active_reservation(session, product)
        if reservation:
            # The product lock serializes every writer to its reservations.
            session.refresh(reservation, with_for_update=True)
            require(data.get("expected_reservation_version") == reservation.row_version,
                    "STALE_VERSION", "关联预约已变化，请刷新后处理")
            reservation.status = "CANCELLED"
            reservation.row_version += 1
            reservation.reason = reason
            reservation.cancel_actor_id = actor.id
            reservation.cancel_type = "VIOLATION"
        touch(product, "VIOLATED")
        action = "TAKE_DOWN"
    else:
        touch(product)
    session.add(ViolationRecord(product_id=product.id, admin_id=actor.id, action=action, reason=reason))
    return "product", product.id, before, product.status
