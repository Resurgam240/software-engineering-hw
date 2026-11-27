"""Business projections, history endpoints, and read-only integrity diagnostics."""

from sqlalchemy import text

from campus_market.integrity import IntegrityInspector
from campus_market.models import Product
from campus_market.errors import DomainError
import pytest


def test_owner_history_contains_admin_and_counterparty_actions(world):
    sale = world.sale()
    reservation = world.reserve(sale)
    world.run(world.seller, "reservation.confirm", world.reservation_tokens(reservation))
    owner = world.queries.history(world.seller, {})
    assert any(row["action"] == "review" for row in owner["items"])
    assert any(row["action"] == "reservation.create" for row in owner["items"])
    buyer = world.queries.history(world.buyer, {})
    assert any(row["action"] == "reservation.confirm" for row in buyer["items"])
    assert all("actor_id" not in row and "role" not in row for row in buyer["items"])
    assert all(row["target_id"] not in (sale["id"], reservation["id"])
               for row in world.queries.history(world.other, {})["items"])
    history = world.queries.product_history(world.seller, sale["id"])
    assert len(history["versions"]) == 1 and history["reviews"][0]["status"] == "APPROVED"


def test_private_audit_query_has_reason_not_message(world):
    reservation = world.reserve(world.sale())
    world.queries.private_message(world.admin, reservation["id"], "VIOLATION", "查看违规线索")
    records = world.queries.private_access_history(world.admin, {"reservation_id": reservation["id"]})
    assert records["total"] == 1
    assert records["items"][0]["reason"] == "查看违规线索"
    assert "original_message" not in records["items"][0]


def test_old_buyer_cannot_read_later_draft(world):
    sale = world.sale()
    reservation = world.reserve(sale)
    world.run(world.buyer, "reservation.cancel", {**world.reservation_tokens(reservation), "reason": "取消"})
    current = world.queries.product(world.seller, sale["id"])
    edited = world.run(world.seller, "product.edit", {**world.product_tokens(current, content=True),
        "title": "尚未公开的新草稿", "price": "80.00", "category": "其他", "condition": "全新"})
    with pytest.raises(DomainError) as failure:
        world.queries.product(world.buyer, edited["id"])
    assert failure.value.code == "NOT_FOUND"
    assert world.queries.reservation(world.buyer, reservation["id"])["snapshot"]["title"] == sale["title"]


def test_integrity_reports_corruption_without_repair(world):
    sale = world.sale()
    inspector = IntegrityInspector(world.db, world.settings.asset_dir)
    assert inspector.inspect()["ok"]
    with world.db.engine.begin() as conn:
        conn.execute(text("UPDATE products SET status='RESERVED' WHERE id=:id"), {"id": sale["id"]})
    try:
        result = inspector.inspect()
        assert {"code": "ACTIVE_STATE_MISMATCH", "target_type": "product", "target_id": sale["id"]} in result["problems"]
        with world.db.sessions() as session:
            assert session.get(Product, sale["id"]).status == "RESERVED"
    finally:
        with world.db.engine.begin() as conn:
            conn.execute(text("UPDATE products SET status='SALE' WHERE id=:id"), {"id": sale["id"]})
