"""Fault/retry atomicity and the actual HTTP security boundary."""

from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select

from campus_market.errors import DomainError
from campus_market.models import OperationReceipt, Reservation
from campus_market.web import create_app


@pytest.mark.parametrize("round_number", range(10))
def test_precommit_failure_leaves_no_business_effect(world, round_number):
    product = world.sale()
    data = {**world.product_tokens(product, content=True), "message": "提交前失败"}
    key = str(uuid4())
    with pytest.raises(DomainError) as failure:
        world.run(world.buyer, "reservation.create", data, key=key, fault="before_commit")
    assert failure.value.code == "INJECTED_FAILURE"
    assert world.queries.product(world.buyer, product["id"])["status"] == "SALE"
    with world.db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Reservation)
                              .where(Reservation.product_id == product["id"])) == 0
        assert session.get(OperationReceipt, (world.buyer.id, key)) is None
    assert world.run(world.buyer, "reservation.create", data, key=key)["status"] == "PENDING"


@pytest.mark.parametrize("round_number", range(10))
def test_postcommit_response_loss_can_recover(world, round_number):
    product = world.sale()
    data = {**world.product_tokens(product, content=True), "message": "提交后响应丢失"}
    key = str(uuid4())
    with pytest.raises(DomainError) as failure:
        world.run(world.buyer, "reservation.create", data, key=key, fault="after_commit")
    assert failure.value.code == "RESPONSE_LOST"
    result = world.run(world.buyer, "reservation.create", data, key=key)
    assert result["status"] == "PENDING"
    with world.db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Reservation)
                              .where(Reservation.product_id == product["id"])) == 1


def test_http_auth_csrf_strict_dto_and_revoke(world, settings):
    with TestClient(create_app(settings)) as client:
        client.get("/market")
        csrf = client.cookies["campus_csrf"]
        headers = {"X-CSRF-Token": csrf}
        assert client.post("/auth/login", json={"username": world.seller.username,
            "password": "TestingPassword!"}).status_code == 403
        assert client.post("/auth/register", headers=headers, json={"username": "forged_admin",
            "password": "Password123!", "role": "ADMIN"}).status_code == 422
        assert client.post("/auth/login", headers={**headers, "Origin": "https://evil.invalid"},
            json={"username": world.seller.username, "password": "TestingPassword!"}).status_code == 403
        login = client.post("/auth/login", headers=headers,
            json={"username": world.seller.username, "password": "TestingPassword!"})
        assert login.status_code == 200
        token = client.cookies["campus_session"]
        headers = {"X-CSRF-Token": client.cookies["campus_csrf"], "Idempotency-Key": str(uuid4())}
        invalid = client.post("/api/products", headers=headers, json={"title": "测试", "actor_id": world.other.id})
        assert invalid.status_code == 422 and "TestingPassword!" not in invalid.text
        response = client.post("/api/products", headers=headers, json={"title": "通过HTTP创建草稿"})
        assert response.status_code == 201
        assert client.get("/api/admin/products").status_code == 403
        assert client.post("/auth/logout", headers=headers).status_code == 200
        client.cookies.set("campus_session", token)
        assert client.get("/api/me").json()["user"] is None


def test_http_all_registered_action_endpoints(world, settings):
    product = world.sale()
    with TestClient(create_app(settings)) as client:
        client.get("/market")
        client.post("/auth/login", headers={"X-CSRF-Token": client.cookies["campus_csrf"]},
                    json={"username": world.buyer.username, "password": "TestingPassword!"})
        headers = {"X-CSRF-Token": client.cookies["campus_csrf"], "Idempotency-Key": str(uuid4())}
        reserve = client.post("/api/reservations", headers=headers,
            json={**world.product_tokens(product, content=True), "message": "HTTP预约"})
        assert reserve.status_code == 201, reserve.text
        reservation = reserve.json()["object"]
        headers["Idempotency-Key"] = str(uuid4())
        cancel = client.post(f"/api/reservations/{reservation['id']}/cancel", headers=headers,
            json={"expected_row_version": reservation["product_row_version"],
                  "expected_reservation_version": reservation["row_version"], "reason": "HTTP取消"})
        assert cancel.status_code == 200, cancel.text
        assert cancel.json()["object"]["status"] == "CANCELLED"
