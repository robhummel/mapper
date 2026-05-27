"""
Generate base64-encoded JPEG thumbnails from photos.

Thumbnails are embedded directly in the HTML to avoid external file dependencies.
"""

import base64
import io
from pathlib import Path

from PIL import Image, ImageOps


THUMB_MAX_SIZE = (400, 400)
THUMB_QUALITY = 72


def generate_thumbnail(photo_path: str | Path, max_size: tuple = THUMB_MAX_SIZE) -> str:
    """
    Generate a base64-encoded JPEG thumbnail.

    Args:
        photo_path: Path to the source image.
        max_size: Maximum (width, height) for the thumbnail.

    Returns:
        Base64-encoded JPEG string (without the data URI prefix).
    """
    path = Path(photo_path)

    with Image.open(path) as img:
        # Auto-rotate based on EXIF orientation tag
        img = ImageOps.exif_transpose(img)

        # Convert to RGB (handles HEIC, PNG with alpha, etc.)
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')

        # Thumbnail preserves aspect ratio and does not upscale
        img.thumbnail(max_size, Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=THUMB_QUALITY, optimize=True)
        buf.seek(0)

    return base64.b64encode(buf.read()).decode('ascii')


def add_thumbnails(photos: list[dict]) -> list[dict]:
    """
    Generate thumbnails for a list of photo dicts and add 'thumbnail_b64' key.

    Args:
        photos: List of photo metadata dicts (from exif_reader).

    Returns:
        Same list, with 'thumbnail_b64' added to each dict.
    """
    total = len(photos)
    for i, photo in enumerate(photos, start=1):
        print(f"  Generating thumbnail {i}/{total}: {photo['filename']}", end='\r')
        try:
            photo['thumbnail_b64'] = generate_thumbnail(photo['path'])
        except Exception as e:
            print(f"\n  ⚠ Could not generate thumbnail for {photo['filename']}: {e}")
            photo['thumbnail_b64'] = None

    print(f"  ✓ {total} thumbnail(s) generated                    ")
    return photos
