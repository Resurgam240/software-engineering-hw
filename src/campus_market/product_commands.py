"""Product lifecycle commands; callers own transaction, receipt, and audit writes."""

from sqlalchemy import delete, select

from campus_market.auth import require_role
from campus_market.errors import require
from campus_market.models import ImageAsset, Product, ProductVersion, ReviewBatch, VersionImage, now
from campus_market.repository import assert_consistent, product_for_update
from campus_market.validation import check_versions, content_fields


def owned_product(session, actor, data):
    """Ownership failures use the same response as unavailable objects."""
    require_role(actor, "USER")
    product = product_for_update(session, data["product_id"])
    require(product.seller_id == actor.id, "NOT_FOUND", "对象不存在或不可访问", 404)
    assert_consistent(session, product)
    check_versions(product, data)
    return product


def add_version(session, actor, product, fields):
    """Insert content and image links after verifying ownership of every asset."""
    images = fields.pop("image_ids")
    for image_id in images:
        asset = session.get(ImageAsset, image_id)
        require(asset is not None and asset.owner_id == actor.id,
                "IMAGE_ACCESS", "图片不存在或不属于当前账号", 422, "image_ids")
    session.add(ProductVersion(product_id=product.id, version=product.content_version, **fields))
    session.flush()
    for position, image_id in enumerate(images, 1):
        session.add(VersionImage(product_id=product.id, version=product.content_version,
                                 position=position, image_id=image_id))


def touch(product, state=None):
    """State changes advance row version; public content version is independent."""
    if state:
        product.status = state
    product.row_version += 1
    product.updated_at = now()


def create_product(session, actor, data):
    """Create a title-bearing draft without pretending that it is publishable."""
    require_role(actor, "USER")
    fields = content_fields(data)
    product = Product(seller_id=actor.id)
    session.add(product)
    session.flush()
    add_version(session, actor, product, fields)
    return "product", product.id, "", "DRAFT"


def edit_product(session, actor, data):
    """Successful public edits withdraw the current sale and create a new version."""
    product = owned_product(session, actor, data)
    require(product.status in ("DRAFT", "REJECTED", "OFF", "SALE"),
            "STATE", "当前状态不能编辑，请先撤回审核或处理预约")
    require(data.get("content_version") == product.content_version,
            "STALE_CONTENT", "内容已变化，请刷新后编辑")
    before = product.status
    fields = content_fields(data)
    product.content_version += 1
    add_version(session, actor, product, fields)
    touch(product, "DRAFT")
    return "product", product.id, before, product.status


def submit_product(session, actor, data):
    """Submit the exact current content and create a distinct review batch."""
    product = owned_product(session, actor, data)
    require(product.status in ("DRAFT", "REJECTED", "OFF"), "STATE", "当前状态不能提交审核")
    require(data.get("content_version") == product.content_version,
            "STALE_CONTENT", "提交内容版本已变化")
    version = session.get(ProductVersion, (product.id, product.content_version))
    content_fields({"title": version.title, "category": version.category, "condition": version.condition,
                    "price": version.price, "description": version.description}, submitting=True)
    before = product.status
    session.add(ReviewBatch(product_id=product.id, content_version=product.content_version))
    touch(product, "PENDING")
    return "product", product.id, before, product.status


def withdraw_product(session, actor, data):
    """A withdrawn batch remains in history and cannot be approved later."""
    product = owned_product(session, actor, data)
    require(product.status == "PENDING", "STATE", "只有待审核商品可以撤回")
    batch = session.scalar(select(ReviewBatch).where(
        ReviewBatch.product_id == product.id, ReviewBatch.status == "PENDING"
    ))
    require(batch is not None and data.get("batch_id") == batch.id,
            "STALE_BATCH", "审核批次已变化，请刷新")
    batch.status = "WITHDRAWN"
    touch(product, "DRAFT")
    return "product", product.id, "PENDING", product.status


def take_down(session, actor, data):
    """Ordinary sellers can only take down unreserved sale items."""
    product = owned_product(session, actor, data)
    require(product.status == "SALE", "STATE", "仅无有效预约的在售商品可主动下架")
    touch(product, "OFF")
    return "product", product.id, "SALE", product.status


def delete_draft(session, actor, data):
    """Delete only never-submitted drafts; audit references intentionally survive."""
    product = owned_product(session, actor, data)
    require(product.status == "DRAFT", "STATE", "只能删除从未提交的草稿")
    reviewed = session.scalar(select(ReviewBatch.id).where(ReviewBatch.product_id == product.id).limit(1))
    require(reviewed is None, "HAS_HISTORY", "已有审核历史的商品不能删除")
    session.execute(delete(VersionImage).where(VersionImage.product_id == product.id))
    session.execute(delete(ProductVersion).where(ProductVersion.product_id == product.id))
    session.delete(product)
    return "deleted", product.id, "DRAFT", "DELETED"
