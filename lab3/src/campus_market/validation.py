"""Field rules shared by draft, submission, and reservation workflows."""

from decimal import Decimal, InvalidOperation
import re
from uuid import UUID

from campus_market.constants import CATEGORIES, CONDITIONS
from campus_market.errors import DomainError, require


def identifier(value: str) -> str:
    """Canonical UUIDs avoid database cast errors on hostile object identifiers."""
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise DomainError("NOT_FOUND", "对象不存在或不可访问", 404) from exc


def account_fields(username: str, password: str, nickname: str = "") -> tuple[str, str]:
    """Registration normalizes ASCII usernames and never accepts a public role."""
    require(bool(re.fullmatch(r"[A-Za-z0-9_]{3,20}", username)),
            "USERNAME", "用户名须为3～20位英文字母、数字或下划线", 422, "username")
    require(8 <= len(password) <= 64, "PASSWORD", "密码长度须为8～64个字符", 422, "password")
    require(len(nickname) <= 40, "NICKNAME", "昵称不超过40字", 422, "nickname")
    return username.lower(), nickname.strip()


def reason_text(value: str, field: str = "reason", maximum: int = 200) -> str:
    """Whitespace-only text is never a valid reason or private message."""
    require(isinstance(value, str), "TEXT", "请输入文字", 422, field)
    value = value.strip()
    require(1 <= len(value) <= maximum, "TEXT_LENGTH", f"请输入1～{maximum}个字符", 422, field)
    return value


def money(value, *, optional: bool = False) -> Decimal | None:
    """Reject excess precision before NUMERIC could silently round a value."""
    if optional and value in (None, ""):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise DomainError("PRICE", "请输入合法价格", 422, "price") from exc
    require(result.is_finite() and Decimal("0.01") <= result <= Decimal("99999.99"),
            "PRICE", "价格须为0.01～99999.99元", 422, "price")
    require(result.as_tuple().exponent >= -2, "PRICE_PRECISION", "价格最多两位小数", 422, "price")
    return result


def content_fields(data: dict, *, submitting: bool = False) -> dict:
    """Draft title alone is sufficient; publishing applies the stricter rules."""
    title = str(data.get("title", "")).strip()
    require(bool(title) and len(title) <= 200, "TITLE", "草稿标题不能为空且不超过200字", 422, "title")
    if submitting:
        require(2 <= len(title) <= 50, "TITLE", "提交标题须为2～50字", 422, "title")
    category = data.get("category") or None
    condition = data.get("condition") or None
    require(category in CATEGORIES or (not submitting and category is None),
            "CATEGORY", "请选择固定分类", 422, "category")
    require(condition in CONDITIONS or (not submitting and condition is None),
            "CONDITION", "请选择成色", 422, "condition")
    description = str(data.get("description", ""))
    require(len(description) <= 500, "DESCRIPTION", "描述不超过500字", 422, "description")
    images = data.get("image_ids", [])
    require(isinstance(images, list) and len(images) <= 3, "IMAGES", "最多选择3张图片", 422, "image_ids")
    images = [identifier(item) for item in images]
    require(len(set(images)) == len(images), "IMAGES", "图片不能重复", 422, "image_ids")
    return {"title": title, "category": category, "condition": condition,
            "price": money(data.get("price"), optional=not submitting),
            "description": description, "image_ids": images}


def check_versions(product, data: dict, reservation=None):
    """Every new state-changing attempt must refer to the current observed rows."""
    require(data.get("expected_row_version") == product.row_version,
            "STALE_VERSION", "商品状态已变化，请刷新后重试")
    if "content_version" in data:
        require(data["content_version"] == product.content_version,
                "STALE_CONTENT", "商品内容已变化，请重新查看")
    if reservation is not None:
        require(data.get("expected_reservation_version") == reservation.row_version,
                "STALE_VERSION", "预约状态已变化，请刷新后重试")
