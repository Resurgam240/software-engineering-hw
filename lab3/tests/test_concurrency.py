"""Five conflict categories, ten rounds each, against real PostgreSQL row locks."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from campus_market.constants import ACTIVE
from campus_market.errors import DomainError
from campus_market.models import Reservation
from campus_market.repository import assert_consistent


def race(functions):
    barrier = Barrier(len(functions))

    def run(function):
        barrier.wait(timeout=30)
        try:
            return ("success", function())
        except DomainError as exc:
            return ("rejected", exc.code)

    with ThreadPoolExecutor(max_workers=len(functions)) as pool:
        return list(pool.map(run, functions))


@pytest.mark.parametrize("round_number", range(10))
def test_twenty_buyers_compete(world, round_number):
    product = world.sale()
    buyers = [world.user() for _ in range(20)]
    results = race([lambda actor=actor: world.reserve(product, actor) for actor in buyers])
    assert sum(result[0] == "success" for result in results) == 1
    assert [value for state, value in results if state == "rejected"] == ["UNAVAILABLE"] * 19
    with world.db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Reservation).where(
            Reservation.product_id == product["id"], Reservation.status.in_(ACTIVE))) == 1


@pytest.mark.parametrize("round_number", range(10))
def test_duplicate_concurrent_requests(world, round_number):
    product = world.sale()
    key = str(uuid4())
    results = race([lambda: world.reserve(product, key=key) for _ in range(5)])
    assert all(state == "success" for state, _ in results)
    assert len({value["id"] for _, value in results}) == 1


@pytest.mark.parametrize("round_number", range(10))
def test_confirm_vs_cancel(world, round_number):
    reservation = world.reserve(world.sale())
    tokens = world.reservation_tokens(reservation)
    results = race([
        lambda: world.run(world.seller, "reservation.confirm", tokens),
        lambda: world.run(world.buyer, "reservation.cancel", {**tokens, "reason": "改变安排"}),
    ])
    assert sorted(state for state, _ in results) == ["rejected", "success"]
    assert [value for state, value in results if state == "rejected"] == ["STALE_VERSION"]
    current = world.queries.reservation(world.buyer, reservation["id"])
    assert (current["status"], current["product_status"]) in (("CONFIRMED", "RESERVED"), ("CANCELLED", "SALE"))


@pytest.mark.parametrize("round_number", range(10))
def test_complete_vs_cancel(world, round_number):
    reservation = world.confirmed()
    tokens = world.reservation_tokens(reservation)
    results = race([
        lambda: world.run(world.seller, "reservation.complete", tokens),
        lambda: world.run(world.buyer, "reservation.cancel", {**tokens, "reason": "取消安排"}),
    ])
    assert sorted(state for state, _ in results) == ["rejected", "success"]
    current = world.queries.reservation(world.buyer, reservation["id"])
    assert (current["status"], current["product_status"]) in (("COMPLETED", "SOLD"), ("CANCELLED", "SALE"))
    expected = 1 if current["status"] == "COMPLETED" else 0
    assert world.queries.statistics(world.seller, {})["count"] == expected


@pytest.mark.parametrize("round_number", range(10))
def test_violation_vs_reserve(world, round_number):
    product = world.sale()
    tokens = world.product_tokens(product, content=True)
    results = race([
        lambda: world.reserve(product),
        lambda: world.run(world.admin, "violation", {**tokens, "reason": "核查违规"}),
    ])
    assert sorted(state for state, _ in results) == ["rejected", "success"]
    current = world.queries.product(world.admin, product["id"])
    assert current["status"] in ("RESERVED", "VIOLATED")
    from campus_market.models import Product
    with world.db.sessions() as session:
        assert_consistent(session, session.get(Product, product["id"]))
