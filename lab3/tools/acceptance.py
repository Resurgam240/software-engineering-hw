"""Real HTTP performance samples and ten clean service-process restart checks.

Only campus_market_test is reset. The development database is never changed.
Fixture insertion is intentionally separate from the measured HTTP workload.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import time
from uuid import uuid4

from alembic import command
from alembic.config import Config
import httpx
from sqlalchemy import select, text

from campus_market.auth import AuthService, PASSWORDS
from campus_market.commands import CommandService
from campus_market.config import Settings
from campus_market.db import Database
from campus_market.models import (
    OperationLog, Product, ProductVersion, Reservation, ReservationSnapshot, ReviewBatch, User,
)

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
URL = "http://127.0.0.1:8001"


def prepare(settings):
    assert settings.database_url.rsplit("/", 1)[-1] == "campus_market_test"
    db = Database(settings)
    with db.engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    original = os.environ["DATABASE_URL"]
    os.environ["DATABASE_URL"] = settings.database_url
    try:
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    finally:
        os.environ["DATABASE_URL"] = original
    users = []
    with db.sessions.begin() as session:
        for index in range(100):
            user = User(username=f"perf_{index:03}", role="ADMIN" if index == 0 else "USER",
                        password_hash=PASSWORDS.hash("AcceptancePassword!"))
            session.add(user)
            users.append(user)
        session.flush()
    seller = users[1]
    products = []
    instant = datetime.now(timezone.utc)
    with db.sessions.begin() as session:
        for index in range(1000):
            product = Product(seller_id=seller.id, status="SOLD" if index < 900 else "SALE",
                              row_version=7, content_version=1, published_at=instant)
            session.add(product)
            products.append(product)
        session.flush()
        for index, product in enumerate(products):
            session.add(ProductVersion(product_id=product.id, version=1, title=f"性能教材 {index:04}",
                category="教材书籍", condition="九成新", price="38.00", description="独立性能测试数据"))
        session.flush()
        historical = []
        for index, product in enumerate(products):
            session.add(ReviewBatch(product_id=product.id, content_version=1, status="APPROVED", admin_id=users[0].id))
            reservation = Reservation(product_id=product.id, buyer_id=users[2 + index % 98].id,
                seller_id=seller.id, status="COMPLETED" if index < 900 else "CANCELLED",
                row_version=3, original_message="性能历史样本", completed_at=instant if index < 900 else None,
                cancel_type=None if index < 900 else "VOLUNTARY", reason="" if index < 900 else "历史取消")
            session.add(reservation)
            historical.append(reservation)
        session.flush()
        for product, reservation in zip(products, historical):
            session.add(ReservationSnapshot(reservation_id=reservation.id, product_id=product.id,
                content_version=1, title=f"性能教材 {products.index(product):04}",
                category="教材书籍", condition="九成新", price="38.00", description="独立性能测试数据"))
            session.add(OperationLog(actor_id=seller.id, role_at_time="USER", target_type="product",
                target_id=product.id, action="acceptance-fixture", result="SUCCESS", after_state=product.status))
    return db, users, products[900:]


class Server:
    """A separately installed ASGI server process stopped with a clean Windows interrupt."""

    def __init__(self, settings):
        self.settings = settings
        self.process = None
        self.log = (ARTIFACTS / "acceptance-server.log").open("a", encoding="utf-8")

    def start(self):
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", 8001)) != 0, "Port 8001 is already occupied"
        env = {**os.environ, "DATABASE_URL": self.settings.database_url, "PYTHONUTF8": "1"}
        self.process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "campus_market.web:create_app", "--factory", "--port", "8001"],
            cwd=ROOT, env=env, stdout=self.log, stderr=self.log,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("Acceptance server stopped unexpectedly; inspect the local server log")
            try:
                if httpx.get(URL + "/health", timeout=1).status_code == 200:
                    return
            except httpx.TransportError:
                pass
            time.sleep(0.1)
        raise TimeoutError("Acceptance server failed to become healthy")

    def stop(self):
        import signal
        if self.process and self.process.poll() is None:
            self.process.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT)
            self.process.wait(timeout=20)

    def close(self):
        self.stop()
        self.log.close()


def snapshot(database):
    """Compare all persisted identifiers and state rather than just record counts."""
    with database.sessions() as session:
        return {
            "products": [tuple(row) for row in session.execute(select(Product.id, Product.status,
                Product.row_version, Product.content_version).order_by(Product.id))],
            "reservations": [tuple(row) for row in session.execute(select(Reservation.id, Reservation.status,
                Reservation.product_id, Reservation.buyer_id, Reservation.seller_id,
                Reservation.original_message, Reservation.completed_at).order_by(Reservation.id))],
            "logs": list(session.scalars(select(OperationLog.id).order_by(OperationLog.id))),
        }


def sample_workload(name, requests):
    """Five separate batches of twenty concurrent HTTP calls, with no discarded samples."""
    samples = []

    def measure(item):
        index, function = item
        started = time.perf_counter()
        wall_start = datetime.now(timezone.utc).isoformat()
        try:
            response = function()
            payload = response.json()
            return {"index": index, "start_utc": wall_start, "seconds": time.perf_counter() - started,
                    "end_utc": datetime.now(timezone.utc).isoformat(),
                    "status": response.status_code, "success": response.status_code in (200, 201),
                    "result_id": payload.get("object", {}).get("id"), "code": payload.get("code", "OK")}
        except (httpx.TransportError, ValueError) as exc:
            return {"index": index, "start_utc": wall_start, "seconds": time.perf_counter() - started,
                    "end_utc": datetime.now(timezone.utc).isoformat(),
                    "status": 0, "success": False, "code": type(exc).__name__}

    for batch in range(5):
        with ThreadPoolExecutor(max_workers=20) as pool:
            samples.extend(pool.map(measure, enumerate(requests[batch * 20:(batch + 1) * 20], batch * 20)))
    within = sum(item["success"] and item["seconds"] <= 2 for item in samples)
    return {"name": name, "batches": 5, "concurrency": 20, "samples": samples,
            "within_2_seconds": within, "passed": within >= 95,
            "over_5_seconds": sum(item["seconds"] > 5 for item in samples),
            "max_seconds": max(item["seconds"] for item in samples)}


def main():
    ARTIFACTS.mkdir(exist_ok=True)
    settings = Settings.from_env(testing=True)
    database, users, products = prepare(settings)
    server = Server(settings)
    try:
        auth = AuthService(database)
        commands = CommandService(database, settings)
        # Five retained products and three active reservations are the minimum restart fixture.
        retained = products[:5]
        for product, buyer in zip(retained[:3], users[2:5]):
            commands.execute(buyer, "reservation.create", str(uuid4()), {
                "product_id": product.id, "expected_row_version": product.row_version,
                "content_version": 1, "message": "重启可靠性样本"})
        before = snapshot(database)
        restarts = []
        server.start()
        for iteration in range(10):
            server.stop()
            server.start()
            assert snapshot(database) == before
            restarts.append({"round": iteration + 1, "passed": True,
                             "product_count": len(before["products"]),
                             "reservation_count": len(before["reservations"]), "log_count": len(before["logs"])})
        # Restore the three fixtures by normal cancellation so all hundred targets are available.
        from campus_market.queries import QueryService
        queries = QueryService(database)
        for buyer in users[2:5]:
            active = queries.reservations(buyer, {"status": "PENDING"})["items"]
            for reservation in active:
                commands.execute(buyer, "reservation.cancel", str(uuid4()), {
                    "reservation_id": reservation["id"], "expected_row_version": reservation["product_row_version"],
                    "expected_reservation_version": reservation["row_version"], "reason": "完成重启验证"})
        anonymous = httpx.Client(base_url=URL, timeout=5, limits=httpx.Limits(max_connections=30))
        query_requests = [lambda: anonymous.get("/api/products", params={"keyword": "性能教材",
                          "category": "教材书籍", "min_price": "30", "max_price": "40"}) for _ in range(100)]
        query_result = sample_workload("combined-query", query_requests)
        query_result["request"] = {"path": "/api/products", "keyword": "性能教材", "category": "教材书籍",
                                   "min_price": "30", "max_price": "40"}
        clients = []
        reserve_requests = []
        inputs = []
        for index, product in enumerate(products):
            buyer = users[2 + index % 98]
            _, token, csrf = auth.login(buyer.username, "AcceptancePassword!")
            client = httpx.Client(base_url=URL, timeout=5,
                                 cookies={"campus_session": token, "campus_csrf": csrf},
                                 headers={"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid4())})
            clients.append(client)
            current = queries.product(buyer, product.id)
            body = {"product_id": product.id, "expected_row_version": current["row_version"],
                    "content_version": 1, "message": "性能测试无冲突预约"}
            inputs.append({"product_id": product.id, "buyer_id": buyer.id, "row_version": current["row_version"]})
            reserve_requests.append(lambda client=client, body=body: client.post("/api/reservations", json=body))
        reserve_result = sample_workload("uncontended-reservation", reserve_requests)
        for client in clients:
            client.close()
        anonymous.close()
        with database.sessions() as session:
            from campus_market.repository import assert_consistent
            for product in session.scalars(select(Product)):
                assert_consistent(session, product)
        result = {"environment": {"os": platform.platform(), "python": sys.version,
            "postgresql": "17.7", "database": "campus_market_test", "seed_accounts": 100,
            "seed_products": 1000, "seed_historical_reservations": 1000,
            "note": "重启验证额外创建3条预约，随后取消；无冲突预约使用100件不同商品。"},
            "restarts": restarts, "query": query_result, "reservation": reserve_result,
            "reservation_inputs": inputs, "invariants_after_workload": True}
        (ARTIFACTS / "acceptance-results.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(json.dumps({"restarts": len(restarts), "query_under_2s": query_result["within_2_seconds"],
                          "reserve_under_2s": reserve_result["within_2_seconds"], "invariants": True}, indent=2))
        assert query_result["passed"] and reserve_result["passed"]
    finally:
        server.close()
        database.close()


if __name__ == "__main__":
    main()
