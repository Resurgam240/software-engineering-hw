"""Repeatable demo fixtures exercise the public service boundary rather than fake UI data."""

from uuid import uuid4

from sqlalchemy import select

from campus_market.auth import AuthService
from campus_market.commands import CommandService
from campus_market.models import Product, User
from campus_market.queries import QueryService

DEMO_PASSWORD = "CampusDemo2026!"


def ensure_account(database, username: str, *, admin=False):
    """Never change the password or role of an existing account during initialization."""
    with database.sessions() as session:
        user = session.scalar(select(User).where(User.username == username))
        if user:
            session.expunge(user)
            return user
    AuthService(database).register(username, DEMO_PASSWORD, username, role="ADMIN" if admin else "USER")
    with database.sessions() as session:
        user = session.scalar(select(User).where(User.username == username))
        session.expunge(user)
        return user


def seed_demo(database, settings) -> dict:
    """A durable seed marker prevents reruns from adding duplicate products."""
    users = {name: ensure_account(database, name, admin=name == "admin_demo")
             for name in ("admin_demo", "seller_demo", "buyer_demo", "buyer_two")}
    seller, admin, buyer = users["seller_demo"], users["admin_demo"], users["buyer_demo"]
    with database.sessions() as session:
        existing = session.scalar(select(Product.id).where(Product.seller_id == seller.id).limit(1))
    if existing:
        return {"created": False, "accounts": list(users), "message": "演示商品已存在，未重复创建"}
    commands = CommandService(database, settings)
    queries = QueryService(database)

    def run(actor, action, data):
        return commands.execute(actor, action, str(uuid4()), data)["object"]

    examples = [
        ("软件工程教材", "教材书籍", "38.00", "少量铅笔标注，无缺页。可在图书馆附近交付。"),
        ("护眼学习台灯", "生活用品", "65.00", "三档色温，功能正常，附电源线。"),
        ("无线头戴耳机", "数码电子", "120.00", "已清洁，充电线齐全。"),
        ("轻薄笔记本电脑", "数码电子", "1880.00", "适合课堂学习，面交时可现场检查。"),
        ("羽毛球拍", "文体用品", "80.00", "一支球拍，附拍袋。"),
        ("木质桌面收纳架", "生活用品", "25.00", "小巧实用，桌面自提。"),
        ("算法导论", "教材书籍", "55.00", "保存完好，适合课程学习。"),
        ("便携数码相机", "数码电子", "680.00", "附电池，可现场试拍。"),
    ]
    for index, (title, category, price, description) in enumerate(examples):
        product = run(seller, "product.create", {
            "title": title, "category": category, "condition": "九成新",
            "price": price, "description": description, "image_ids": [],
        })
        if index == 5:
            continue
        product = run(seller, "product.submit", {"product_id": product["id"],
            "expected_row_version": product["row_version"], "content_version": product["content_version"]})
        if index == 6:
            continue
        product = run(admin, "review", {"product_id": product["id"], "batch_id": product["review_batch_id"],
            "content_version": product["content_version"], "expected_row_version": product["row_version"],
            "decision": "APPROVE", "reason": ""})
        if index not in (0, 7):
            continue
        reservation = run(buyer, "reservation.create", {"product_id": product["id"],
            "expected_row_version": product["row_version"], "content_version": product["content_version"],
            "message": "周五下午可以在图书馆门口交付吗？"})
        reservation = run(seller, "reservation.confirm", {"reservation_id": reservation["id"],
            "expected_row_version": reservation["product_row_version"],
            "expected_reservation_version": reservation["row_version"]})
        if index == 7:
            run(seller, "reservation.complete", {"reservation_id": reservation["id"],
                "expected_row_version": reservation["product_row_version"],
                "expected_reservation_version": reservation["row_version"]})
    return {"created": True, "accounts": list(users), "statistics": queries.statistics(seller, {})}
