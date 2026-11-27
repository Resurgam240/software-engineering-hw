"""Immutable local images with content verification and reference-aware access."""

from io import BytesIO
from pathlib import Path
import warnings

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select

from campus_market.auth import require_role
from campus_market.errors import DomainError, require
from campus_market.models import ImageAsset, Product, Reservation, SnapshotImage, VersionImage, new_id
from campus_market.validation import identifier


class AssetService:
    """Writing a file first may leave an orphan, but never a committed missing reference."""

    def __init__(self, database, directory: Path):
        self.database = database
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def upload(self, actor, content: bytes, filename: str) -> dict:
        """Check extension, decoded type, size, and image integrity before persistence."""
        actor = require_role(actor, "USER")
        require(0 < len(content) <= 5 * 1024 * 1024, "IMAGE_SIZE", "图片不得为空且不超过5MB", 422)
        extension = Path(filename).suffix.lower()
        require(extension in (".jpg", ".jpeg", ".png"), "IMAGE_TYPE", "仅支持JPG/PNG图片", 422)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(content)) as image:
                    image_format = image.format
                    require(image.width * image.height <= 25_000_000, "IMAGE_PIXELS", "图片像素过大", 422)
                    image.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError,
                Image.DecompressionBombWarning) as exc:
            raise DomainError("IMAGE_CONTENT", "图片损坏或无法识别", 422) from exc
        expected = "PNG" if extension == ".png" else "JPEG"
        require(image_format == expected, "IMAGE_TYPE", "图片内容与扩展名不一致", 422)
        image_id = new_id()
        key = image_id + (".png" if expected == "PNG" else ".jpg")
        with (self.directory / key).open("xb") as stream:
            stream.write(content)
        with self.database.sessions.begin() as session:
            session.add(ImageAsset(id=image_id, owner_id=actor.id, storage_key=key,
                                    mime="image/png" if expected == "PNG" else "image/jpeg",
                                    byte_size=len(content)))
        return {"id": image_id, "url": f"/images/{image_id}"}

    def read(self, actor, image_id: str) -> tuple[Path, str]:
        """Do not expose draft assets or arbitrary old versions via a public directory."""
        with self.database.sessions() as session:
            asset = session.get(ImageAsset, identifier(image_id))
            require(asset is not None, "NOT_FOUND", "图片不存在或不可访问", 404)
            allowed = actor is not None and asset.owner_id == actor.id
            public = session.scalar(select(Product.id).join(VersionImage,
                (VersionImage.product_id == Product.id) & (VersionImage.version == Product.content_version))
                .where(VersionImage.image_id == image_id, Product.status == "SALE").limit(1))
            allowed = allowed or public is not None
            if actor and not allowed:
                historical = select(Reservation.id).join(SnapshotImage,
                    SnapshotImage.reservation_id == Reservation.id).where(SnapshotImage.image_id == image_id)
                if actor.role != "ADMIN":
                    historical = historical.where((Reservation.buyer_id == actor.id) |
                                                  (Reservation.seller_id == actor.id))
                allowed = session.scalar(historical.limit(1)) is not None
                if actor.role == "ADMIN":
                    allowed = allowed or session.scalar(select(Product.id).join(VersionImage,
                        VersionImage.product_id == Product.id).where(VersionImage.image_id == image_id,
                        Product.status != "DRAFT").limit(1)) is not None
            require(allowed, "NOT_FOUND", "图片不存在或不可访问", 404)
            path = self.directory / asset.storage_key
            require(path.is_file(), "ASSET_UNAVAILABLE", "图片文件暂不可用", 503)
            return path, asset.mime
