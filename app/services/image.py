import io
import logging
from typing import Tuple
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)


class InvalidImageError(Exception):
    """Raised when an uploaded image is invalid or cannot be processed."""
    pass


class ImageProcessingService:
    ALLOWED_FORMATS = {"JPEG", "JPG", "PNG", "WEBP", "MPO"}
    MAX_DIMENSION = 1024
    JPEG_QUALITY = 80

    @classmethod
    def process_image(
        cls,
        image_bytes: bytes,
        max_size_bytes: int = 10 * 1024 * 1024
    ) -> Tuple[bytes, str]:
        """
        Validates, downscales, and optimizes an image for Gemini API.
        Never saves to disk. Returns (processed_bytes, mime_type).
        """
        if not image_bytes:
            raise InvalidImageError("Файл пуст.")

        if len(image_bytes) > max_size_bytes:
            raise InvalidImageError(
                f"Размер изображения превышает допустимый предел ({max_size_bytes // (1024 * 1024)} МБ)."
            )

        try:
            input_stream = io.BytesIO(image_bytes)
            with Image.open(input_stream) as img:
                img_format = (img.format or "").upper()
                if img_format not in cls.ALLOWED_FORMATS:
                    raise InvalidImageError(
                        f"Неподдерживаемый формат изображения ({img_format}). Пожалуйста, отправьте JPEG, PNG или WEBP."
                    )

                # Correct EXIF orientation if present
                try:
                    img = ImageOps.exif_transpose(img)
                except Exception:
                    pass

                # Convert to RGB if necessary (e.g. RGBA, Grayscale, CMYK)
                if img.mode in ("RGBA", "LA", "P"):
                    # Create white background for alpha channel
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    background.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
                    img = background
                elif img.mode != "RGB":
                    img = img.convert("RGB")

                # Downscale if larger than max dimension
                width, height = img.size
                if max(width, height) > cls.MAX_DIMENSION:
                    scale = cls.MAX_DIMENSION / max(width, height)
                    new_width = int(width * scale)
                    new_height = int(height * scale)
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                # Save as optimized JPEG
                output_stream = io.BytesIO()
                img.save(output_stream, format="JPEG", quality=cls.JPEG_QUALITY, optimize=True)
                output_bytes = output_stream.getvalue()

                return output_bytes, "image/jpeg"

        except InvalidImageError:
            raise
        except Exception as e:
            logger.error(f"Image processing failed: {e}", exc_info=True)
            raise InvalidImageError("Не удалось прочитать изображение. Возможно, файл повреждён.")
