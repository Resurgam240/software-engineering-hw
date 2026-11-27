"""Business acceptance tests verify effects, permissions, and historical evidence."""

from io import BytesIO
from uuid import uuid4

from PIL import Image
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from campus_market.assets import AssetService
from campus_market.auth import AuthService
from campus_market.errors import DomainError
from campus_market.models import (
    OperationLog, PrivateAccessLog, Product, ProductVersion, Reservation, User,
)
from campus_market.validation import account_fields, content_fields


def rejected(code, callback):
    with pytest.raises(DomainError) as failure:
        callback()
    assert failure.value.code == code


@pytest.mark.parametrize("username,password", [("ab", "12345678"), ("中文用户", "12345678"),
                                               ("valid", "short"), ("a" * 21, "12345678")])
def test_account_boundaries(username, password):
    with pytest.raises(DomainError):
        account_fields(username, password)


def test_registration_case_duplicate_and_no_secret(world):
    auth = AuthService(world.db)
    name = "Case" + uuid4().hex[:8]
    result = auth.register(name, "Password123!")
    assert result["role"] == "USER" and "password_hash" not in result
    rejected("USERNAME_EXISTS", lambda: auth.register(name.upper(), "Password123!"))
    with world.db.sessions() as session:
        user = session.get(User, result["id"])
        assert user.password_hash.startswith("$argon2id$")
    for username, password in [(name, "wrong"), ("missing_user", "wrong")]:
        rejected("BAD_CREDENTIALS", lambda: auth.login(username, password))


@pytest.mark.parametrize("fields", [{"price": "0"}, {"price": "100000"}, {"price": "1.001"},
                                   {"price": "NaN"}, {"title": ""}, {"category": "不存在"},
                                   {"description": "x" * 501}, {"image_ids": ["bad-id"]}])
def test_invalid_content(fields):
    with pytest.raises(DomainError):
        content_fields({"title": "测试教材", "category": "教材书籍", "condition": "全新",
                        "price": "1.00", **fields}, submitting=True)


@pytest.mark.parametrize("price", ["0.01", "99999.99"])
def test_price_closed_boundaries(price):
    assert str(content_fields({"title": "商品", "category": "其他", "condition": "全新", "price": price},
                              submitting=True)["price"]) == price


def test_draft_and_submission_rules(world):
    draft = world.draft(title="单", category=None, condition=None, price=None)
    rejected("TITLE", lambda: world.submit(draft))
    rejected("FORBIDDEN", lambda: world.run(world.admin, "product.create", {"title": "草稿"}))
    rejected("NOT_FOUND", lambda: world.run(world.other, "product.take-down", world.product_tokens(draft)))
    rejected("LOGIN_REQUIRED", lambda: world.commands.execute(None, "product.create", str(uuid4()), {"title": "A"}))


def test_approval_withdrawal_old_batch_and_rejection(world):
    submitted = world.submit(world.draft())
    withdrawn = world.run(world.seller, "product.withdraw", {
        **world.product_tokens(submitted), "batch_id": submitted["review_batch_id"]})
    resubmitted = world.submit(withdrawn)
    rejected("STALE_BATCH", lambda: world.run(world.admin, "review", {
        **world.product_tokens(resubmitted, content=True), "batch_id": submitted["review_batch_id"],
        "decision": "APPROVE"}))
    rejected("TEXT_LENGTH", lambda: world.review(resubmitted, "REJECT", "  "))
    refused = world.review(resubmitted, "REJECT", "请补充商品描述")
    assert refused["status"] == "REJECTED" and refused["review_reason"] == "请补充商品描述"
    assert world.review(world.submit(refused))["status"] == "SALE"


def test_edit_new_version_and_conflict(world):
    sale = world.sale()
    data = {**world.product_tokens(sale, content=True), "title": "修改后的教材", "price": "45.00",
            "category": "教材书籍", "condition": "全新"}
    edited = world.run(world.seller, "product.edit", data)
    assert edited["status"] == "DRAFT" and edited["content_version"] == sale["content_version"] + 1
    rejected("STALE_VERSION", lambda: world.run(world.seller, "product.edit", data))
    with world.db.sessions() as session:
        assert session.get(ProductVersion, (sale["id"], sale["content_version"])).title == sale["title"]
    rejected("NOT_FOUND", lambda: world.queries.product(None, sale["id"]))


def test_delete_only_new_draft_and_keep_log(world):
    draft = world.draft()
    deleted = world.run(world.seller, "product.delete", world.product_tokens(draft))
    assert deleted["deleted"] is True
    with world.db.sessions() as session:
        assert session.get(Product, draft["id"]) is None
        assert session.scalar(select(func.count()).select_from(OperationLog)
                              .where(OperationLog.target_id == draft["id"])) == 2
    old = world.submit(world.draft())
    old = world.run(world.seller, "product.withdraw", {**world.product_tokens(old),
                                                      "batch_id": old["review_batch_id"]})
    rejected("HAS_HISTORY", lambda: world.run(world.seller, "product.delete", world.product_tokens(old)))


def test_take_down_and_republish(world):
    off = world.run(world.seller, "product.take-down", world.product_tokens(world.sale()))
    assert off["status"] == "OFF"
    assert world.review(world.submit(off))["status"] == "SALE"


def test_reserve_permissions_and_same_buyer_cross_device(world):
    sale = world.sale()
    rejected("OWN_PRODUCT", lambda: world.reserve(sale, world.seller))
    rejected("FORBIDDEN", lambda: world.reserve(sale, world.admin))
    first = world.reserve(sale)
    assert world.reserve(sale)["id"] == first["id"]
    rejected("UNAVAILABLE", lambda: world.reserve(sale, world.other))
    rejected("NOT_FOUND", lambda: world.queries.reservation(world.other, first["id"]))
    rejected("STATE", lambda: world.run(world.seller, "product.take-down", {
        "product_id": sale["id"], "expected_row_version": first["product_row_version"]}))


@pytest.mark.parametrize("message", ["", "  ", "x" * 201])
def test_message_boundaries(world, message):
    sale = world.sale()
    rejected("TEXT_LENGTH", lambda: world.run(world.buyer, "reservation.create", {
        **world.product_tokens(sale, content=True), "message": message}))


def test_reservation_confirm_cancel_and_reject(world):
    reservation = world.reserve(world.sale())
    rejected("STATE", lambda: world.run(world.seller, "reservation.cancel", {
        **world.reservation_tokens(reservation), "reason": "不想卖了"}))
    rejected("STATE", lambda: world.run(world.seller, "reservation.complete", world.reservation_tokens(reservation)))
    rejected("FORBIDDEN", lambda: world.run(world.buyer, "reservation.confirm", world.reservation_tokens(reservation)))
    refused = world.run(world.seller, "reservation.reject", {**world.reservation_tokens(reservation), "reason": "时间不合适"})
    assert refused["status"] == "REJECTED" and refused["product_status"] == "SALE"
    fresh = world.queries.product(world.buyer, refused["product_id"])
    reservation = world.reserve(fresh)
    cancelled = world.run(world.buyer, "reservation.cancel", {
        **world.reservation_tokens(reservation), "reason": "临时改变安排"})
    assert cancelled["status"] == "CANCELLED" and cancelled["product_status"] == "SALE"
    rejected("TERMINAL_STATE", lambda: world.run(world.seller, "reservation.confirm", world.reservation_tokens(cancelled)))


def test_completion_statistics_and_terminal_state(world):
    confirmed = world.confirmed()
    before = world.queries.statistics(world.seller, {})
    data = world.reservation_tokens(confirmed)
    key = str(uuid4())
    result = world.run(world.seller, "reservation.complete", data, key=key)
    assert result["status"] == "COMPLETED" and result["product_status"] == "SOLD"
    assert world.run(world.seller, "reservation.complete", data, key=key)["id"] == result["id"]
    after = world.queries.statistics(world.seller, {})
    assert after["count"] == before["count"] + 1 and after["total_price"] == "38.00"
    assert world.queries.statistics(world.buyer, {})["count"] == 0
    assert world.queries.statistics(world.seller, {"category": "数码电子"})["count"] == 0
    rejected("TERMINAL_STATE", lambda: world.run(world.buyer, "reservation.cancel", {
        **world.reservation_tokens(result), "reason": "完成后不能取消"}))


@pytest.mark.parametrize("actor_name", ["buyer", "seller"])
def test_confirmed_cancellation_by_either_party(world, actor_name):
    confirmed = world.confirmed()
    cancelled = world.run(getattr(world, actor_name), "reservation.cancel", {
        **world.reservation_tokens(confirmed), "reason": "双方另行安排"})
    assert cancelled["product_status"] == "SALE"


def test_idempotency_and_late_requests(world):
    sale = world.sale()
    key = str(uuid4())
    data = {**world.product_tokens(sale, content=True), "message": "相同内容重试"}
    reservation = world.run(world.buyer, "reservation.create", data, key=key)
    rejected("KEY_REUSED", lambda: world.run(world.buyer, "reservation.create", {**data, "message": "不同"}, key=key))
    cancelled = world.run(world.buyer, "reservation.cancel", {**world.reservation_tokens(reservation), "reason": "取消"})
    replay = world.run(world.buyer, "reservation.create", data, key=key)
    assert replay["status"] == "CANCELLED"
    assert world.queries.product(world.buyer, sale["id"])["status"] == "SALE"
    assert world.reserve(world.queries.product(world.buyer, sale["id"]))["id"] != cancelled["id"]


@pytest.mark.parametrize("state", ["PENDING", "SALE", "RESERVED", "OFF", "SOLD"])
def test_violation_all_supported_states(world, state):
    if state == "SOLD":
        reservation = world.confirmed()
        done = world.run(world.seller, "reservation.complete", world.reservation_tokens(reservation))
        product = world.queries.product(world.admin, done["product_id"])
    elif state == "PENDING":
        product = world.submit(world.draft())
    else:
        product = world.sale()
        if state == "RESERVED":
            reservation = world.reserve(product)
            product = world.queries.product(world.admin, product["id"])
        if state == "OFF":
            product = world.run(world.seller, "product.take-down", world.product_tokens(product))
    data = {**world.product_tokens(product, content=True), "batch_id": product["review_batch_id"], "reason": "测试违规核查"}
    if state == "RESERVED":
        data["expected_reservation_version"] = reservation["row_version"]
    result = world.run(world.admin, "violation", data)
    assert result["status"] == ("SOLD" if state == "SOLD" else "REJECTED" if state == "PENDING" else "VIOLATED")
    if state == "RESERVED":
        history = world.queries.reservation(world.buyer, reservation["id"])
        assert history["status"] == "CANCELLED" and history["cancel_type"] == "VIOLATION"
        rejected("TERMINAL_STATE", lambda: world.run(world.buyer, "reservation.cancel", {
            **world.reservation_tokens(history), "reason": "不得恢复在售"}))
    if state == "SOLD":
        assert world.queries.statistics(world.seller, {})["count"] == 1


def test_private_access_and_append_only_database(world):
    reservation = world.reserve(world.sale())
    public = world.queries.reservation(world.admin, reservation["id"])
    assert "original_message" not in public
    assert all("original_message" not in item for item in world.queries.reservations(world.admin, {})["items"])
    rejected("TEXT_LENGTH", lambda: world.queries.private_message(world.admin, reservation["id"], "VIOLATION", ""))
    rejected("FORBIDDEN", lambda: world.queries.private_message(world.other, reservation["id"], "VIOLATION", "检查"))
    rejected("AUDIT_UNAVAILABLE", lambda: world.queries.private_message(world.admin, reservation["id"], "VIOLATION", "检查", fail=True))
    for _ in range(2):
        assert world.queries.private_message(world.admin, reservation["id"], "STATE_CHECK", "核对状态")["original_message"]
    with world.db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(PrivateAccessLog)
                              .where(PrivateAccessLog.reservation_id == reservation["id"])) == 2
    with pytest.raises(DBAPIError), world.db.engine.begin() as conn:
        conn.execute(text("UPDATE operation_logs SET result='SUCCESS'"))


def test_images_and_snapshot_survive_edit(world):
    assets = AssetService(world.db, world.settings.asset_dir)
    output = BytesIO()
    Image.new("RGB", (40, 30), "blue").save(output, format="PNG")
    image = assets.upload(world.seller, output.getvalue(), "photo.png")
    rejected("IMAGE_TYPE", lambda: assets.upload(world.seller, output.getvalue(), "photo.jpg"))
    rejected("IMAGE_CONTENT", lambda: assets.upload(world.seller, b"fake", "photo.png"))
    rejected("NOT_FOUND", lambda: assets.read(None, image["id"]))
    product = world.draft(image_ids=[image["id"]])
    product = world.review(world.submit(product))
    assert assets.read(None, image["id"])[0].is_file()
    reservation = world.reserve(product)
    cancelled = world.run(world.buyer, "reservation.cancel", {**world.reservation_tokens(reservation), "reason": "改日"})
    current = world.queries.product(world.seller, product["id"])
    world.run(world.seller, "product.edit", {**world.product_tokens(current, content=True), "title": "修改后商品",
        "category": "其他", "condition": "全新", "price": "99.00", "image_ids": []})
    old = world.queries.reservation(world.buyer, cancelled["id"])
    assert old["snapshot"]["price"] == "38.00" and old["snapshot"]["image_ids"] == [image["id"]]
    assert assets.read(world.buyer, image["id"])[0].is_file()
    rejected("NOT_FOUND", lambda: assets.read(world.other, image["id"]))


def test_query_scopes_and_invalid_filters(world):
    draft = world.draft()
    sale = world.sale()
    rejected("NOT_FOUND", lambda: world.queries.product(world.admin, draft["id"]))
    results = world.queries.products(None, {"keyword": "测试教材", "min_price": "38", "max_price": "38"})
    assert any(item["id"] == sale["id"] for item in results["items"]) or results["total"] > 20
    assert all(item["status"] == "SALE" for item in results["items"])
    assert world.queries.products(None, {"status": "DRAFT"})["total"] == 0
    assert all(item["seller_id"] == world.seller.id for item in world.queries.products(world.seller, {}, "mine")["items"])
    rejected("PRICE_RANGE", lambda: world.queries.products(None, {"min_price": "40", "max_price": "10"}))
    rejected("SORT", lambda: world.queries.products(None, {"sort": "price; DROP TABLE users"}))
    rejected("DATE_RANGE", lambda: world.queries.statistics(world.seller, {"from": "2026-12-01", "to": "2026-11-01"}))
    rejected("NOT_FOUND", lambda: world.queries.product(world.buyer, "not-a-uuid"))
