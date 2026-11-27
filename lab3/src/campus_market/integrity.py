"""Read-only diagnostics for retained data; this module never repairs business state."""

from sqlalchemy import func, select

from campus_market.constants import ACTIVE
from campus_market.models import (
    ImageAsset, Product, ProductVersion, Reservation, ReservationSnapshot,
    ReviewBatch, SnapshotImage, User, VersionImage,
)


class IntegrityInspector:
    """Check invariants in a consistent read snapshot without exposing private content."""

    def __init__(self, database, asset_dir):
        self.database = database
        self.asset_dir = asset_dir

    def inspect(self) -> dict:
        """Return anomaly identifiers and counts; no message, secret, or password leaves storage."""
        with self.database.sessions.begin() as session:
            session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            problems = []
            self._products(session, problems)
            self._reservations(session, problems)
            self._images(session, problems)
            counts = {
                name: session.scalar(select(func.count()).select_from(model))
                for name, model in (("users", User), ("products", Product), ("reservations", Reservation),
                                    ("versions", ProductVersion), ("images", ImageAsset))
            }
            return {"ok": not problems, "counts": counts, "problems": problems,
                    "policy": "只诊断，不修改数据；异常由开发或维护人员受控处理。"}

    @staticmethod
    def _problem(problems, code, kind, target_id):
        problems.append({"code": code, "target_type": kind, "target_id": target_id})

    def _products(self, session, problems):
        """Current content, active occupancy, completion, and pending review must agree."""
        for product in session.scalars(select(Product)):
            version = session.get(ProductVersion, (product.id, product.content_version))
            if version is None:
                self._problem(problems, "MISSING_CURRENT_VERSION", "product", product.id)
            active = list(session.scalars(select(Reservation).where(
                Reservation.product_id == product.id, Reservation.status.in_(ACTIVE))))
            completed = list(session.scalars(select(Reservation.id).where(
                Reservation.product_id == product.id, Reservation.status == "COMPLETED")))
            pending = list(session.scalars(select(ReviewBatch).where(
                ReviewBatch.product_id == product.id, ReviewBatch.status == "PENDING")))
            if len(active) > 1 or bool(active) != (product.status == "RESERVED"):
                self._problem(problems, "ACTIVE_STATE_MISMATCH", "product", product.id)
            if len(completed) > 1 or bool(completed) != (product.status == "SOLD"):
                self._problem(problems, "COMPLETED_STATE_MISMATCH", "product", product.id)
            if len(pending) > 1 or bool(pending) != (product.status == "PENDING"):
                self._problem(problems, "REVIEW_STATE_MISMATCH", "product", product.id)
            if pending and pending[0].content_version != product.content_version:
                self._problem(problems, "REVIEW_CONTENT_MISMATCH", "product", product.id)
            seller = session.get(User, product.seller_id)
            if seller is None or seller.role != "USER":
                self._problem(problems, "INVALID_SELLER", "product", product.id)

    def _reservations(self, session, problems):
        """Snapshot public data and immutable parties must remain internally consistent."""
        for reservation in session.scalars(select(Reservation)):
            product = session.get(Product, reservation.product_id)
            snapshot = session.get(ReservationSnapshot, reservation.id)
            buyer = session.get(User, reservation.buyer_id)
            if product is None or product.seller_id != reservation.seller_id:
                self._problem(problems, "SELLER_MISMATCH", "reservation", reservation.id)
            if buyer is None or buyer.role != "USER" or reservation.buyer_id == reservation.seller_id:
                self._problem(problems, "INVALID_BUYER", "reservation", reservation.id)
            if snapshot is None:
                self._problem(problems, "MISSING_SNAPSHOT", "reservation", reservation.id)
                continue
            if snapshot.product_id != reservation.product_id:
                self._problem(problems, "SNAPSHOT_PRODUCT_MISMATCH", "reservation", reservation.id)
            version = session.get(ProductVersion, (snapshot.product_id, snapshot.content_version))
            fields = ("title", "category", "condition", "price", "description")
            differs = version is None or any(
                getattr(version, field) != getattr(snapshot, field) for field in fields
            )
            if differs:
                self._problem(problems, "SNAPSHOT_CONTENT_MISMATCH", "reservation", reservation.id)
            version_images = list(session.scalars(select(VersionImage.image_id).where(
                VersionImage.product_id == snapshot.product_id,
                VersionImage.version == snapshot.content_version
            ).order_by(VersionImage.position)))
            snapshot_images = list(session.scalars(select(SnapshotImage.image_id).where(
                SnapshotImage.reservation_id == reservation.id).order_by(SnapshotImage.position)))
            if version_images != snapshot_images:
                self._problem(problems, "SNAPSHOT_IMAGES_MISMATCH", "reservation", reservation.id)

    def _images(self, session, problems):
        """Committed assets may never point to missing files or a changed byte size."""
        for asset in session.scalars(select(ImageAsset)):
            path = self.asset_dir / asset.storage_key
            if not path.is_file():
                self._problem(problems, "MISSING_ASSET", "image", asset.id)
            elif path.stat().st_size != asset.byte_size:
                self._problem(problems, "ASSET_SIZE_MISMATCH", "image", asset.id)
