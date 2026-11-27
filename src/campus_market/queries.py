"""Read-side authorization, bounded searches, historical views, and exact statistics."""

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import String, cast, func, or_, select

from campus_market.auth import require_role, require_user
from campus_market.errors import DomainError, require
from campus_market.models import (
    OperationLog, PrivateAccessLog, Product, ProductVersion, Reservation,
    ReservationSnapshot, ReviewBatch, ViolationRecord,
)
from campus_market.repository import can_see_product, product_view, reservation_view
from campus_market.validation import identifier, money, reason_text


def pagination(query: dict) -> tuple[int, int]:
    """Bound pages before issuing offsets; public page size is always twenty."""
    try:
        page = int(query.get("page", 1))
    except (ValueError, TypeError) as exc:
        raise DomainError("PAGE", "页码须为正整数", 422, "page") from exc
    require(1 <= page <= 100000, "PAGE", "页码超出范围", 422, "page")
    return page, (page - 1) * 20


def date_bounds(query: dict) -> tuple[datetime | None, datetime | None]:
    """UI dates mean inclusive Asia/Shanghai calendar days, stored and queried in UTC."""
    local = timezone(timedelta(hours=8))
    try:
        start = date.fromisoformat(query["from"]) if query.get("from") else None
        end = date.fromisoformat(query["to"]) if query.get("to") else None
    except ValueError as exc:
        raise DomainError("DATE", "日期格式须为YYYY-MM-DD", 422) from exc
    require(not (start and end) or start <= end, "DATE_RANGE", "开始日期不能晚于结束日期", 422)
    lower = datetime.combine(start, time.min, local) if start else None
    upper = datetime.combine(end + timedelta(days=1), time.min, local) if end else None
    return lower, upper


class QueryService:
    """Queries choose server-side scopes before applying user-supplied filters."""

    def __init__(self, database):
        self.database = database

    def products(self, actor, query: dict, scope: str = "public") -> dict:
        """Search only current content; arbitrary SQL identifiers are never accepted."""
        page, offset = pagination(query)
        statement = select(Product).join(ProductVersion, (
            (ProductVersion.product_id == Product.id) &
            (ProductVersion.version == Product.content_version)
        ))
        if scope == "public":
            statement = statement.where(Product.status == "SALE")
        elif scope == "mine":
            actor = require_role(actor, "USER")
            statement = statement.where(Product.seller_id == actor.id)
        else:
            require_role(actor, "ADMIN")
            statement = statement.where(Product.status != "DRAFT")
        if query.get("status"):
            statement = statement.where(Product.status == query["status"])
        keyword = str(query.get("keyword", "")).strip()
        require(len(keyword) <= 200, "KEYWORD", "关键词不超过200字", 422)
        if keyword:
            pattern = "%" + keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            statement = statement.where(or_(ProductVersion.title.ilike(pattern, escape="\\"),
                                            ProductVersion.description.ilike(pattern, escape="\\")))
        if query.get("category"):
            statement = statement.where(ProductVersion.category == query["category"])
        low = money(query.get("min_price"), optional=True)
        high = money(query.get("max_price"), optional=True)
        require(low is None or high is None or low <= high,
                "PRICE_RANGE", "最低价不能高于最高价", 422, "min_price")
        if low is not None:
            statement = statement.where(ProductVersion.price >= low)
        if high is not None:
            statement = statement.where(ProductVersion.price <= high)
        sorts = {"latest": Product.published_at.desc().nulls_last(),
                 "price_asc": ProductVersion.price.asc().nulls_last(),
                 "price_desc": ProductVersion.price.desc().nulls_last()}
        require(query.get("sort", "latest") in sorts, "SORT", "不支持的排序方式", 422)
        with self.database.sessions() as session:
            total = session.scalar(select(func.count()).select_from(statement.subquery()))
            rows = session.scalars(statement.order_by(sorts[query.get("sort", "latest")], Product.id)
                                   .offset(offset).limit(20))
            return {"items": [product_view(session, row) for row in rows], "total": total, "page": page}

    def product(self, actor, product_id: str) -> dict:
        """Public, owner, administrator, and historical-party detail access."""
        with self.database.sessions() as session:
            product = session.get(Product, identifier(product_id))
            require(product is not None and can_see_product(session, actor, product),
                    "NOT_FOUND", "对象不存在或不可访问", 404)
            result = product_view(session, product)
            if actor and (actor.id == product.seller_id or actor.role == "ADMIN"):
                result["violations"] = [
                    {"action": row.action, "reason": row.reason, "created_at": row.created_at}
                    for row in session.scalars(select(ViolationRecord)
                        .where(ViolationRecord.product_id == product.id).order_by(ViolationRecord.created_at))
                ]
            return result

    def reservations(self, actor, query: dict) -> dict:
        """Administrative lists expose metadata, never private message bodies."""
        actor = require_user(actor)
        page, offset = pagination(query)
        statement = select(Reservation)
        if actor.role != "ADMIN":
            scope = query.get("scope", "buyer")
            require(scope in ("buyer", "seller"), "SCOPE", "请选择买家或卖家范围", 422)
            column = Reservation.seller_id if scope == "seller" else Reservation.buyer_id
            statement = statement.where(column == actor.id)
        if query.get("status"):
            statement = statement.where(Reservation.status == query["status"])
        with self.database.sessions() as session:
            total = session.scalar(select(func.count()).select_from(statement.subquery()))
            rows = session.scalars(statement.order_by(Reservation.created_at.desc(), Reservation.id)
                                   .offset(offset).limit(20))
            return {"items": [reservation_view(session, row, actor) for row in rows],
                    "total": total, "page": page}

    def reservation(self, actor, reservation_id: str) -> dict:
        """Only parties receive the original message through the ordinary detail API."""
        actor = require_user(actor)
        with self.database.sessions() as session:
            row = session.get(Reservation, identifier(reservation_id))
            require(row is not None, "NOT_FOUND", "对象不存在或不可访问", 404)
            return reservation_view(session, row, actor, detail=True)

    def statistics(self, actor, query: dict) -> dict:
        """Aggregate once from immutable prices and completed reservations."""
        actor = require_user(actor)
        lower, upper = date_bounds(query)
        statement = select(Reservation, ReservationSnapshot).join(
            ReservationSnapshot, ReservationSnapshot.reservation_id == Reservation.id
        ).where(Reservation.status == "COMPLETED")
        if actor.role != "ADMIN":
            statement = statement.where(Reservation.seller_id == actor.id)
        if lower:
            statement = statement.where(Reservation.completed_at >= lower)
        if upper:
            statement = statement.where(Reservation.completed_at < upper)
        if query.get("category"):
            statement = statement.where(ReservationSnapshot.category == query["category"])
        page, offset = pagination(query)
        with self.database.sessions() as session:
            subquery = statement.subquery()
            count, total = session.execute(select(func.count(), func.coalesce(func.sum(subquery.c.price), 0))
                                           .select_from(subquery)).one()
            rows = session.execute(statement.order_by(Reservation.completed_at.desc(), Reservation.id)
                                   .offset(offset).limit(20))
            items = [{"reservation_id": row.id, "title": snapshot.title, "category": snapshot.category,
                      "price": str(snapshot.price), "completed_at": row.completed_at}
                     for row, snapshot in rows]
            return {"count": count, "total_price": str(total), "items": items, "page": page,
                    "notice": "按预约时标价计算，未核验实际付款。"}

    def history(self, actor, query: dict) -> dict:
        """User history is a restricted projection, not raw administrative logs."""
        actor = require_user(actor)
        page, offset = pagination(query)
        statement = select(OperationLog)
        if actor.role != "ADMIN":
            own_products = select(cast(Product.id, String)).where(Product.seller_id == actor.id)
            own_reservations = select(cast(Reservation.id, String)).where(
                (Reservation.buyer_id == actor.id) | (Reservation.seller_id == actor.id)
            )
            related_success = (OperationLog.result == "SUCCESS") & (
                ((OperationLog.target_type == "product") &
                 OperationLog.target_id.in_(own_products))
                | ((OperationLog.target_type == "reservation") &
                   OperationLog.target_id.in_(own_reservations))
            )
            statement = statement.where((OperationLog.actor_id == actor.id) | related_success)
            statement = statement.where(OperationLog.action != "private-message-access")
        elif query.get("actor_id"):
            statement = statement.where(OperationLog.actor_id == identifier(query["actor_id"]))
        if query.get("target_id"):
            statement = statement.where(OperationLog.target_id == query["target_id"])
        if query.get("action"):
            statement = statement.where(OperationLog.action == query["action"])
        lower, upper = date_bounds(query)
        if lower:
            statement = statement.where(OperationLog.created_at >= lower)
        if upper:
            statement = statement.where(OperationLog.created_at < upper)
        with self.database.sessions() as session:
            total = session.scalar(select(func.count()).select_from(statement.subquery()))
            rows = session.scalars(statement.order_by(OperationLog.created_at.desc(), OperationLog.id)
                                   .offset(offset).limit(20))
            items = [{"id": row.id, "action": row.action, "target_id": row.target_id,
                      "before_state": row.before_state, "after_state": row.after_state,
                      "result": row.result, "failure_code": row.failure_code, "created_at": row.created_at,
                      **({"actor_id": row.actor_id, "role": row.role_at_time}
                         if actor.role == "ADMIN" else {})}
                     for row in rows]
            return {"items": items, "total": total, "page": page}

    def product_history(self, actor, product_id: str) -> dict:
        """Owners and administrators can inspect retained versions and review batches."""
        actor = require_user(actor)
        product_id = identifier(product_id)
        with self.database.sessions() as session:
            product = session.get(Product, product_id)
            require(product is not None and (product.seller_id == actor.id or
                    (actor.role == "ADMIN" and product.status != "DRAFT")),
                    "NOT_FOUND", "对象不存在或不可访问", 404)
            versions = session.scalars(select(ProductVersion).where(
                ProductVersion.product_id == product_id).order_by(ProductVersion.version.desc()))
            batches = session.scalars(select(ReviewBatch).where(
                ReviewBatch.product_id == product_id).order_by(ReviewBatch.created_at.desc()))
            return {
                "product_id": product_id,
                "versions": [{"version": row.version, "title": row.title, "category": row.category,
                              "condition": row.condition, "price": str(row.price) if row.price else None,
                              "description": row.description} for row in versions],
                "reviews": [{"id": row.id, "content_version": row.content_version, "status": row.status,
                             "reason": row.reason, "created_at": row.created_at} for row in batches],
            }

    def private_access_history(self, actor, query: dict) -> dict:
        """Administrative access records are searchable without copying message bodies."""
        require_role(actor, "ADMIN")
        page, offset = pagination(query)
        statement = select(PrivateAccessLog)
        if query.get("reservation_id"):
            statement = statement.where(PrivateAccessLog.reservation_id == identifier(query["reservation_id"]))
        if query.get("admin_id"):
            statement = statement.where(PrivateAccessLog.admin_id == identifier(query["admin_id"]))
        lower, upper = date_bounds(query)
        if lower:
            statement = statement.where(PrivateAccessLog.created_at >= lower)
        if upper:
            statement = statement.where(PrivateAccessLog.created_at < upper)
        with self.database.sessions() as session:
            total = session.scalar(select(func.count()).select_from(statement.subquery()))
            rows = session.scalars(statement.order_by(PrivateAccessLog.created_at.desc(),
                                                      PrivateAccessLog.id)
                                   .offset(offset).limit(20))
            return {"page": page, "total": total, "items": [
                {"id": row.id, "admin_id": row.admin_id, "reservation_id": row.reservation_id,
                 "purpose": row.purpose, "reason": row.reason, "created_at": row.created_at}
                for row in rows
            ]}

    def private_message(self, actor, reservation_id: str, purpose: str, reason: str, *, fail=False) -> dict:
        """Never return private content before its access record has committed."""
        actor = require_role(actor, "ADMIN")
        reason = reason_text(reason)
        require(purpose in ("VIOLATION", "STATE_CHECK"), "PURPOSE", "请选择违规核查或状态排查", 422)
        with self.database.sessions.begin() as session:
            reservation = session.get(Reservation, identifier(reservation_id))
            require(reservation is not None, "NOT_FOUND", "对象不存在或不可访问", 404)
            session.add(PrivateAccessLog(admin_id=actor.id, reservation_id=reservation.id,
                                         purpose=purpose, reason=reason))
            session.add(OperationLog(actor_id=actor.id, role_at_time=actor.role, target_type="reservation",
                                     target_id=reservation.id, action="private-message-access",
                                     result="SUCCESS"))
            if fail:
                raise DomainError("AUDIT_UNAVAILABLE", "访问留痕保存失败，未展示留言", 503)
            message = reservation.original_message
        return {"original_message": message, "notice": "本次访问已记录原因、操作者和时间。"}
