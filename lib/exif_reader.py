"""
EXIF data extraction from GPS-tagged photos.

Extracts: GPS coordinates, timestamp, user notes, camera info.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import exifread
from PIL import Image
from PIL.ExifTags import TAGS


SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.heic', '.png', '.tiff', '.tif'}


def _dms_to_decimal(dms_values, ref: str) -> Optional[float]:
    """Convert degrees/minutes/seconds EXIF values to decimal degrees."""
    try:
        degrees = float(dms_values[0].num) / float(dms_values[0].den)
        minutes = float(dms_values[1].num) / float(dms_values[1].den)
        seconds = float(dms_values[2].num) / float(dms_values[2].den)
        decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
        if ref in ('S', 'W'):
            decimal = -decimal
        return decimal
    except (IndexError, ZeroDivisionError, AttributeError, TypeError):
        return None


def _extract_gps(tags: dict) -> tuple[Optional[float], Optional[float]]:
    """Extract latitude and longitude from exifread tags."""
    lat = lon = None

    lat_tag = tags.get('GPS GPSLatitude')
    lat_ref = tags.get('GPS GPSLatitudeRef')
    lon_tag = tags.get('GPS GPSLongitude')
    lon_ref = tags.get('GPS GPSLongitudeRef')

    if lat_tag and lat_ref:
        lat = _dms_to_decimal(lat_tag.values, str(lat_ref))
    if lon_tag and lon_ref:
        lon = _dms_to_decimal(lon_tag.values, str(lon_ref))

    return lat, lon


def _extract_timestamp(tags: dict) -> Optional[datetime]:
    """Extract the original capture timestamp."""
    for field in ('EXIF DateTimeOriginal', 'EXIF DateTimeDigitized', 'Image DateTime'):
        tag = tags.get(field)
        if tag:
            try:
                return datetime.strptime(str(tag), '%Y:%m:%d %H:%M:%S')
            except ValueError:
                continue
    return None


def _extract_notes(tags: dict) -> Optional[str]:
    """Extract user notes from common EXIF comment fields."""
    candidates = [
        'EXIF UserComment',
        'Image ImageDescription',
        'Image XPComment',
        'Image XPSubject',
    ]
    for field in candidates:
        tag = tags.get(field)
        if tag:
            value = str(tag).strip()
            # exifread sometimes returns 'ASCII\x00\x00\x00' or similar for empty fields
            cleaned = value.replace('\x00', '').replace('ASCII', '').strip()
            if cleaned and cleaned.lower() not in ('', 'binary comment'):
                return cleaned
    return None


def _extract_camera(tags: dict) -> Optional[str]:
    """Extract camera make/model."""
    make = tags.get('Image Make')
    model = tags.get('Image Model')
    parts = []
    if make:
        parts.append(str(make).strip())
    if model:
        model_str = str(model).strip()
        # Avoid duplicating make in model (e.g. "Apple iPhone 15")
        if parts and model_str.startswith(parts[0]):
            parts = [model_str]
        else:
            parts.append(model_str)
    return ' '.join(parts) if parts else None


def read_photo(path: str | Path, yaml_override: Optional[dict] = None) -> Optional[dict]:
    """
    Read EXIF data from a photo file.

    Args:
        path: Path to the image file.
        yaml_override: Optional dict with keys 'notes', 'lat', 'lon' from YAML config.

    Returns:
        Dict with photo metadata, or None if the file cannot be processed.
    """
    path = Path(path)
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return None

    override = yaml_override or {}

    try:
        with open(path, 'rb') as f:
            tags = exifread.process_file(f, details=False)
    except Exception as e:
        print(f"  ⚠ Could not read EXIF from {path.name}: {e}")
        tags = {}

    lat, lon = _extract_gps(tags)
    timestamp = _extract_timestamp(tags)
    notes = _extract_notes(tags)
    camera = _extract_camera(tags)

    # Apply YAML overrides
    if 'lat' in override:
        lat = float(override['lat'])
    if 'lon' in override:
        lon = float(override['lon'])
    if 'notes' in override and override['notes']:
        notes = str(override['notes'])  # YAML notes override EXIF notes

    return {
        'filename': path.name,
        'path': str(path),
        'lat': lat,
        'lon': lon,
        'timestamp': timestamp,
        'timestamp_display': timestamp.strftime('%-d %b %Y at %-I:%M %p') if timestamp else None,
        'notes': notes,
        'camera': camera,
        'has_gps': lat is not None and lon is not None,
    }


def read_photos_dir(
    directory: str | Path,
    yaml_photos: Optional[dict] = None,
) -> list[dict]:
    """
    Read all supported photos from a directory.

    Args:
        directory: Path to the photos folder.
        yaml_photos: Optional dict keyed by filename with per-photo overrides.

    Returns:
        List of photo metadata dicts, sorted by timestamp (chronological).
        Photos without GPS are excluded with a warning.
    """
    directory = Path(directory)
    yaml_photos = {k.lower(): v for k, v in (yaml_photos or {}).items()}

    photos = []
    skipped = []

    candidates = sorted(
        p for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    if not candidates:
        print(f"  ⚠ No supported image files found in {directory}")
        return []

    for photo_path in candidates:
        override = yaml_photos.get(photo_path.name.lower(), {})
        data = read_photo(photo_path, override)
        if data is None:
            continue
        if not data['has_gps']:
            skipped.append(photo_path.name)
            continue
        photos.append(data)

    if skipped:
        print(f"  ⚠ Skipped {len(skipped)} photo(s) with no GPS data: {', '.join(skipped)}")
        print(f"    (Add lat/lon under that filename in your YAML config to include them.)")

    # Sort chronologically; photos without timestamps go last
    photos.sort(key=lambda p: p['timestamp'] or datetime.max)

    # Assign sequential hazard numbers
    for i, photo in enumerate(photos, start=1):
        photo['number'] = i

    print(f"  ✓ {len(photos)} photo(s) loaded with GPS coordinates")
    return photos
