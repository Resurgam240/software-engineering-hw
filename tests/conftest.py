"""Integration fixtures use a dedicated real PostgreSQL database, never SQLite."""

from dataclasses import replace
import os
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import text

from campus_market.auth import AuthService
from campus_market.commands import CommandService
from campus_market.config import Settings
from campus_market.db import Database
from campus_market.models import User
from campus_market.queries import QueryService


@pytest.fixture(scope="session")
def settings():
    settings = Settings.from_env(testing=True)
    assert settings.database_url.rsplit("/", 1)[-1] == "campus_market_test"
    return replace(settings, asset_dir=settings.asset_dir.parent / "test-images")


@pytest.fixture(scope="session")
def database(settings):
    db = Database(settings)
    with db.engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    original = os.environ["DATABASE_URL"]
    os.environ["DATABASE_URL"] = settings.database_url
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        os.environ["DATABASE_URL"] = original
    yield db
    db.close()


@pytest.fixture
def world(database, settings):
    return World(database, settings)


class World:
    """Create independent records so concurrency tests cannot interfere across cases."""

    def __init__(self, database, settings):
        self.db = database
        self.settings = settings
        self.commands = CommandService(database, settings)
        self.queries = QueryService(database)
        self.seller = self.user()
        self.buyer = self.user()
        self.other = self.user()
        self.admin = self.user(admin=True)

    def user(self, *, admin=False):
        result = AuthService(self.db).register("u" + uuid4().hex[:15], "TestingPassword!",
                                              role="ADMIN" if admin else "USER")
        with self.db.sessions() as session:
            user = session.get(User, result["id"])
            session.expunge(user)
            return user

    def run(self, actor, action, data, *, key=None, fault=""):
        return self.commands.execute(actor, action, key or str(uuid4()), data, fault=fault)["object"]

    def draft(self, **fields):
        return self.run(self.seller, "product.create", {
            "title": "测试教材", "category": "教材书籍", "condition": "九成新", "price": "38.00",
            "description": "用于真实数据库集成验证", "image_ids": [], **fields,
        })

    def submit(self, product):
        return self.run(self.seller, "product.submit", self.product_tokens(product, content=True))

    def sale(self):
        product = self.submit(self.draft())
        return self.review(product)

    def review(self, product, decision="APPROVE", reason=""):
        return self.run(self.admin, "review", {**self.product_tokens(product, content=True),
            "batch_id": product["review_batch_id"], "decision": decision, "reason": reason})

    @staticmethod
    def product_tokens(product, *, content=False):
        return {"product_id": product["id"], "expected_row_version": product["row_version"],
                **({"content_version": product["content_version"]} if content else {})}

    @staticmethod
    def reservation_tokens(reservation):
        return {"reservation_id": reservation["id"], "expected_row_version": reservation["product_row_version"],
                "expected_reservation_version": reservation["row_version"]}

    def reserve(self, product, actor=None, *, key=None):
        return self.run(actor or self.buyer, "reservation.create", {
            **self.product_tokens(product, content=True), "message": "周五图书馆面交"}, key=key)

    def confirmed(self):
        reservation = self.reserve(self.sale())
        return self.run(self.seller, "reservation.confirm", self.reservation_tokens(reservation))
