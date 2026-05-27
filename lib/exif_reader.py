"""
EXIF data extraction from GPS-tagged photos.

Extracts: GPS coordinates, DOP (accuracy), timestamp, user notes, camera info.
Interpolates position for photos with null-island (0,0) coords or very high DOP.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import exifread
from PIL import Image
from PIL.ExifTags import TAGS


SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.heic', '.png', '.tiff', '.tif'}

# GPSDOP threshold above which a fix is considered too poor to trust.
# DOP 5052 ≈ 5000 m error; DOP 50 ≈ ~250–500 m. Anything above 50 gets interpolated.
DOP_THRESHOLD = 50.0


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


def _extract_dop(tags: dict) -> Optional[float]:
    """Extract GPSDOP (Dilution of Precision). Lower is better; >50 is very poor."""
    tag = tags.get('GPS GPSDOP')
    if not tag:
        return None
    try:
        v = tag.values[0]
        return float(v.num) / float(v.den)
    except (IndexError, ZeroDivisionError, AttributeError):
        try:
            return float(str(tag))
        except ValueError:
            return None


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
        if parts and model_str.startswith(parts[0]):
            parts = [model_str]
        else:
            parts.append(model_str)
    return ' '.join(parts) if parts else None


def _needs_interpolation(photo: dict, dop_threshold: float = DOP_THRESHOLD) -> bool:
    """Return True if this photo's position should be replaced by interpolation."""
    lat, lon = photo.get('lat'), photo.get('lon')
    if lat is None or lon is None:
        return False  # No GPS at all — already excluded upstream
    if lat == 0.0 and lon == 0.0:
        return True   # Null island — GPS fix failure
    dop = photo.get('gps_dop')
    if dop is not None and dop > dop_threshold:
        return True   # DOP too high — position untrustworthy
    return False


def _interpolate_positions(
    photos: list[dict],
    dop_threshold: float = DOP_THRESHOLD,
) -> list[dict]:
    """
    For photos at (0,0) or with DOP above threshold, linearly interpolate
    their position from the nearest valid photos before and after by timestamp.

    - If valid neighbours exist on both sides: time-weighted linear interpolation.
    - If only one side has a valid neighbour: copy that position.
    - If no valid neighbours exist at all: leave position but mark invalid.

    Adds to each affected photo:
        interpolated (bool): True
        interpolation_reason (str): human-readable explanation
    """
    # Anchors: photos with trustworthy positions
    def is_anchor(p):
        if not p.get('has_gps'):
            return False
        lat, lon = p.get('lat', 0), p.get('lon', 0)
        if lat == 0.0 and lon == 0.0:
            return False
        dop = p.get('gps_dop')
        if dop is not None and dop > dop_threshold:
            return False
        return True

    anchor_indices = [i for i, p in enumerate(photos) if is_anchor(p)]

    flagged = [(i, p) for i, p in enumerate(photos) if _needs_interpolation(p, dop_threshold)]
    if not flagged:
        return photos

    for idx, photo in flagged:
        original_lat = photo['lat']
        original_lon = photo['lon']
        original_dop = photo.get('gps_dop')
        t_curr = photo.get('timestamp')

        before = [i for i in anchor_indices if i < idx]
        after  = [i for i in anchor_indices if i > idx]

        if before and after:
            prev_p = photos[before[-1]]
            next_p = photos[after[0]]
            t_prev = prev_p.get('timestamp')
            t_next = next_p.get('timestamp')

            # Time-based fraction; fall back to index fraction
            if t_prev and t_next and t_curr and t_next != t_prev:
                total   = (t_next - t_prev).total_seconds()
                elapsed = (t_curr - t_prev).total_seconds()
                frac    = max(0.0, min(1.0, elapsed / total if total else 0.5))
            else:
                span = after[0] - before[-1]
                frac = (idx - before[-1]) / span if span else 0.5

            photo['lat'] = prev_p['lat'] + frac * (next_p['lat'] - prev_p['lat'])
            photo['lon'] = prev_p['lon'] + frac * (next_p['lon'] - prev_p['lon'])

        elif before:
            photo['lat'] = photos[before[-1]]['lat']
            photo['lon'] = photos[before[-1]]['lon']

        elif after:
            photo['lat'] = photos[after[0]]['lat']
            photo['lon'] = photos[after[0]]['lon']

        else:
            # No valid neighbours — can't interpolate; mark for exclusion
            photo['has_gps'] = False
            photo['interpolated'] = False
            continue

        photo['interpolated'] = True

        if original_lat == 0.0 and original_lon == 0.0:
            photo['interpolation_reason'] = 'GPS signal unavailable — location estimated'
        elif original_dop and original_dop > dop_threshold:
            photo['interpolation_reason'] = f'Poor GPS accuracy (DOP {original_dop:.0f}) — location estimated'
        else:
            photo['interpolation_reason'] = 'Location estimated'

    n_interp = sum(1 for _, p in flagged if p.get('interpolated'))
    n_drop   = sum(1 for _, p in flagged if not p.get('interpolated'))
    if n_interp:
        print(f"  ℹ {n_interp} photo(s) had invalid/poor GPS — positions interpolated from neighbouring timestamps")
    if n_drop:
        print(f"  ⚠ {n_drop} photo(s) could not be interpolated (no valid neighbours) — excluded")

    return photos


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

    lat, lon   = _extract_gps(tags)
    dop        = _extract_dop(tags)
    timestamp  = _extract_timestamp(tags)
    notes      = _extract_notes(tags)
    camera     = _extract_camera(tags)

    # YAML overrides take precedence over EXIF
    if 'lat' in override:
        lat = float(override['lat'])
    if 'lon' in override:
        lon = float(override['lon'])
    if 'notes' in override and override['notes']:
        notes = str(override['notes'])

    return {
        'filename':          path.name,
        'path':              str(path),
        'lat':               lat,
        'lon':               lon,
        'gps_dop':           dop,
        'timestamp':         timestamp,
        'timestamp_display': timestamp.strftime('%-d %b %Y at %-I:%M %p') if timestamp else None,
        'notes':             notes,
        'camera':            camera,
        'has_gps':           lat is not None and lon is not None,
        'interpolated':      False,
        'interpolation_reason': None,
    }


def read_photos_dir(
    directory: str | Path,
    yaml_photos: Optional[dict] = None,
    dop_threshold: float = DOP_THRESHOLD,
) -> list[dict]:
    """
    Read all supported photos from a directory.

    Returns:
        List of photo metadata dicts, sorted by timestamp (chronological).
        Photos with no GPS are excluded. Photos with (0,0) or high DOP are
        position-interpolated from neighbouring timestamps and marked with
        interpolated=True.
    """
    directory   = Path(directory)
    yaml_photos = {k.lower(): v for k, v in (yaml_photos or {}).items()}

    photos  = []
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

    # Sort chronologically; photos without timestamps go last
    photos.sort(key=lambda p: p['timestamp'] or datetime.max)

    # Interpolate null-island and high-DOP positions
    photos = _interpolate_positions(photos, dop_threshold)

    # Remove any that still have no valid GPS after interpolation
    photos = [p for p in photos if p.get('has_gps')]

    # Assign sequential hazard numbers
    for i, photo in enumerate(photos, start=1):
        photo['number'] = i

    print(f"  ✓ {len(photos)} photo(s) ready")
    return photos
