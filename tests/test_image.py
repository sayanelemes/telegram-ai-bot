import io
import pytest
from PIL import Image
from app.services.image import ImageProcessingService, InvalidImageError


def create_test_image(format="JPEG", size=(200, 200), mode="RGB") -> bytes:
    buffer = io.BytesIO()
    img = Image.new(mode, size, color=(255, 100, 50))
    img.save(buffer, format=format)
    return buffer.getvalue()


def test_process_valid_jpeg():
    raw_bytes = create_test_image(format="JPEG", size=(300, 300))
    proc_bytes, mime = ImageProcessingService.process_image(raw_bytes)
    assert mime == "image/jpeg"
    assert len(proc_bytes) > 0

    with Image.open(io.BytesIO(proc_bytes)) as img:
        assert img.format == "JPEG"
        assert img.size == (300, 300)


def test_process_png_with_alpha():
    raw_bytes = create_test_image(format="PNG", size=(400, 400), mode="RGBA")
    proc_bytes, mime = ImageProcessingService.process_image(raw_bytes)
    assert mime == "image/jpeg"

    with Image.open(io.BytesIO(proc_bytes)) as img:
        assert img.format == "JPEG"
        assert img.mode == "RGB"
        assert img.size == (400, 400)


def test_downscale_large_image():
    raw_bytes = create_test_image(format="JPEG", size=(3200, 2400))
    proc_bytes, mime = ImageProcessingService.process_image(raw_bytes)

    with Image.open(io.BytesIO(proc_bytes)) as img:
        assert max(img.size) <= ImageProcessingService.MAX_DIMENSION
        assert img.size[0] == ImageProcessingService.MAX_DIMENSION


def test_empty_image_error():
    with pytest.raises(InvalidImageError, match="Файл пуст"):
        ImageProcessingService.process_image(b"")


def test_size_limit_exceeded():
    raw_bytes = create_test_image(format="JPEG", size=(100, 100))
    with pytest.raises(InvalidImageError, match="превышает допустимый предел"):
        ImageProcessingService.process_image(raw_bytes, max_size_bytes=10)


def test_corrupted_image():
    with pytest.raises(InvalidImageError):
        ImageProcessingService.process_image(b"not_an_image_random_bytes_12345")
