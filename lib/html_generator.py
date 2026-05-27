"""
Render the Leaflet map HTML from a Jinja2 template.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


TEMPLATES_DIR = Path(__file__).parent.parent / 'templates'


def _slug(text: str) -> str:
    """Convert text to a URL-safe filename slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text.strip('-')


def build_report_meta(
    photos: list[dict],
    name: str | None,
    location: str | None,
    description: str | None,
) -> dict:
    """Build the report-level metadata dict."""
    # Infer date from the earliest photo timestamp
    timestamps = [p['timestamp'] for p in photos if p.get('timestamp')]
    date_str = None
    if timestamps:
        earliest = min(timestamps)
        date_str = earliest.strftime('%-d %B %Y')

    report_name = name or 'Trail Hazard Report'
    slug = _slug(report_name)
    if date_str:
        slug_date = min(timestamps).strftime('%Y-%m-%d')
        slug = f"{slug}-{slug_date}"

    return {
        'name': report_name,
        'location': location,
        'description': description,
        'date': date_str,
        'photo_count': len(photos),
        'slug': slug,
        'generated_at': datetime.now().isoformat(),
    }


def render_map(
    photos: list[dict],
    report: dict,
    output_path: str | Path,
) -> Path:
    """
    Render the map HTML and write it to output_path.

    Args:
        photos: List of photo metadata dicts (with thumbnail_b64 and optional share_url).
        report: Report-level metadata dict (from build_report_meta).
        output_path: Where to write the HTML file.

    Returns:
        The resolved output path.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=False)
    template = env.get_template('map.html.j2')

    # Prepare a clean copy of photos for JSON embedding
    # (avoid embedding raw paths or internal keys)
    photos_for_js = []
    for p in photos:
        photos_for_js.append({
            'number': p['number'],
            'filename': p['filename'],
            'lat': p['lat'],
            'lon': p['lon'],
            'timestamp_display': p.get('timestamp_display'),
            'notes': p.get('notes'),
            'camera': p.get('camera'),
            'thumbnail_b64': p.get('thumbnail_b64'),
            'share_url': p.get('share_url'),
            'interpolated': p.get('interpolated', False),
            'interpolation_reason': p.get('interpolation_reason'),
        })

    html = template.render(
        photos_json=json.dumps(photos_for_js),
        report_json=json.dumps(report),
        report=report,
    )

    output_path.write_text(html, encoding='utf-8')
    return output_path
