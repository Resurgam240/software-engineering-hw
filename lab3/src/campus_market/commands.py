"""Command facade coordinates locks, idempotency, atomic audit, and safe retries."""

import hashlib
import hmac
import json
from uuid import UUID

from sqlalchemy import select, text

from campus_market import governance, product_commands, trade_commands
from campus_market.auth import AuthService, require_user
from campus_market.errors import DomainError, require
from campus_market.models import OperationLog, OperationReceipt, Product, Reservation
from campus_market.repository import assert_consistent, can_see_product, product_view, reservation_view

HANDLERS = {
    "product.create": product_commands.create_product,
    "product.edit": product_commands.edit_product,
    "product.submit": product_commands.submit_product,
    "product.withdraw": product_commands.withdraw_product,
    "product.take-down": product_commands.take_down,
    "product.delete": product_commands.delete_draft,
    "review": governance.review, "violation": governance.violation,
    "reservation.create": trade_commands.reserve,
    "reservation.confirm": trade_commands.confirm,
    "reservation.reject": trade_commands.reject,
    "reservation.cancel": trade_commands.cancel,
    "reservation.complete": trade_commands.complete,
}


class CommandService:
    """No handler may commit; result, log, and receipt succeed or fail together."""

    def __init__(self, database, settings):
        self.database = database
        self.settings = settings

    def execute(self, actor, action: str, key: str, data: dict, *, fault: str = "") -> dict:
        """Execute a fresh command or return its currently authorized original object."""
        actor = require_user(actor)
        require(action in HANDLERS, "COMMAND", "未知业务命令", 422)
        try:
            key = str(UUID(key))
        except (ValueError, TypeError, AttributeError) as exc:
            raise DomainError("OPERATION_KEY", "请提供UUID操作标识", 422) from exc
        require(not fault or self.settings.testing, "FORBIDDEN", "不允许故障注入", 403)
        encoded = json.dumps({"action": action, "data": data}, sort_keys=True,
                             ensure_ascii=False, default=str).encode()
        request_hash = hmac.new(self.settings.secret.encode(), encoded, hashlib.sha256).hexdigest()
        try:
            with self.database.sessions.begin() as session:
                # A key lock precedes business row locks. This also serializes the same key
                # accidentally reused against different products without a unique-index race.
                lock_key = int.from_bytes(hashlib.sha256(f"{actor.id}:{key}".encode()).digest()[:8],
                                          "big", signed=True)
                session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
                receipt = session.get(OperationReceipt, (actor.id, key))
                if receipt:
                    require(hmac.compare_digest(receipt.request_hash, request_hash),
                            "KEY_REUSED", "同一操作标识不能用于不同内容")
                    return self._result(session, actor, receipt.result_kind, receipt.result_id, replay=True)
                kind, target_id, before, after = HANDLERS[action](session, actor, dict(data))
                session.flush()
                self._check_result(session, kind, target_id)
                session.add(OperationLog(actor_id=actor.id, role_at_time=actor.role,
                                         target_type=kind, target_id=target_id, action=action,
                                         before_state=before, after_state=after, result="SUCCESS"))
                session.add(OperationReceipt(actor_id=actor.id, operation_key=key, request_hash=request_hash,
                                             result_kind=kind, result_id=target_id))
                if fault == "before_commit":
                    raise DomainError("INJECTED_FAILURE", "测试：提交前失败", 503)
                result = self._result(session, actor, kind, target_id)
            if fault == "after_commit":
                raise DomainError("RESPONSE_LOST", "测试：提交成功后响应丢失，请用原标识重试", 503)
            return result
        except DomainError as exc:
            AuthService(self.database).record_failure(actor.id, action, exc.code,
                data.get("product_id", data.get("reservation_id", "")))
            raise

    @staticmethod
    def _check_result(session, kind, target_id):
        """Verify cross-table state before writing the successful command receipt."""
        if kind == "product":
            assert_consistent(session, session.get(Product, target_id))
        elif kind == "reservation":
            reservation = session.get(Reservation, target_id)
            assert_consistent(session, session.get(Product, reservation.product_id))

    @staticmethod
    def _result(session, actor, kind, target_id, *, replay=False):
        """Replays read current projections and re-check object permissions."""
        if kind == "deleted":
            value = {"id": target_id, "deleted": True}
        elif kind == "product":
            product = session.scalar(select(Product).where(Product.id == target_id))
            if product is None:
                value = {"id": target_id, "deleted": True}
            else:
                require(can_see_product(session, actor, product), "NOT_FOUND", "对象不存在或不可访问", 404)
                value = product_view(session, product)
        else:
            reservation = session.get(Reservation, target_id)
            value = reservation_view(session, reservation, actor, detail=True)
        return {"kind": kind, "object": value, "replayed": replay}
