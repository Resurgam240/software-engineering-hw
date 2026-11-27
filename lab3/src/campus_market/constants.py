"""Stable domain vocabulary aligned with the submitted UML state machines."""

from enum import StrEnum


class ProductStatus(StrEnum):
    """Eight product states; SOLD and VIOLATED cannot return to sale."""

    DRAFT = "DRAFT"
    PENDING = "PENDING"
    REJECTED = "REJECTED"
    SALE = "SALE"
    RESERVED = "RESERVED"
    OFF = "OFF"
    VIOLATED = "VIOLATED"
    SOLD = "SOLD"


class ReservationStatus(StrEnum):
    """Only PENDING and CONFIRMED occupy a product."""

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"


ACTIVE = (ReservationStatus.PENDING, ReservationStatus.CONFIRMED)
CATEGORIES = ("教材书籍", "数码电子", "生活用品", "文体用品", "其他")
CONDITIONS = ("全新", "九成新", "八成新", "七成新及以下")
STATUS_LABELS = {
    "DRAFT": "草稿", "PENDING": "待处理", "REJECTED": "已驳回",
    "SALE": "在售", "RESERVED": "已预约", "OFF": "已下架",
    "VIOLATED": "违规下架", "SOLD": "已成交", "CONFIRMED": "已确认",
    "CANCELLED": "已取消", "COMPLETED": "已完成", "APPROVED": "已通过",
    "WITHDRAWN": "已撤回",
}
