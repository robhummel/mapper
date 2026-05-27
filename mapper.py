#!/usr/bin/env python3
"""
mapper.py — Trail Hazard Photo Map Generator

Takes a directory of GPS-tagged photos and generates a mobile-friendly
Leaflet.js map published to GitHub Pages.

Usage:
    python mapper.py --photos /path/to/photos [options]

Options:
    --photos PATH           Directory containing hike photos (required)
    --config FILE           YAML config file (optional)
    --name TEXT             Report name (overrides YAML)
    --location TEXT         Location description (overrides YAML)
    --description TEXT      Report description (overrides YAML)
    --onedrive-path PATH    OneDrive folder path for share links (optional)
    --no-push               Generate HTML without pushing to GitHub Pages
    --output-dir DIR        Output directory (default: ./output)
    --open                  Open the generated HTML in a browser after generation
"""

import argparse
import os
import sys
import webbrowser
from pathlib import Path

from dotenv import load_dotenv
import yaml

# ── Project lib ─────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from lib.exif_reader import read_photos_dir
from lib.thumbnail import add_thumbnails
from lib.html_generator import build_report_meta, render_map
from lib.github_deploy import deploy, OUTPUT_DIR


def load_yaml_config(path: str | Path) -> dict:
    """Load and return a YAML config file."""
    try:
        with open(path, 'r') as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        print(f"  ✗ Config file not found: {path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"  ✗ YAML parse error in {path}: {e}")
        sys.exit(1)


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description='Generate a trail hazard map from GPS-tagged photos.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--photos', required=True, metavar='PATH',
                        help='Directory containing hike photos')
    parser.add_argument('--config', metavar='FILE',
                        help='YAML config file (optional)')
    parser.add_argument('--name', metavar='TEXT',
                        help='Report name')
    parser.add_argument('--location', metavar='TEXT',
                        help='Location description')
    parser.add_argument('--description', metavar='TEXT',
                        help='Report description')
    parser.add_argument('--onedrive-path', metavar='PATH',
                        help='OneDrive folder path for share links (e.g. "Hikes/Trail-2026")')
    parser.add_argument('--no-push', action='store_true',
                        help='Generate HTML without pushing to GitHub Pages')
    parser.add_argument('--output-dir', metavar='DIR', default=str(OUTPUT_DIR),
                        help='Output directory (default: ./docs)')
    parser.add_argument('--open', action='store_true',
                        help='Open the generated HTML in a browser')
    args = parser.parse_args()

    photos_dir = Path(args.photos)
    if not photos_dir.is_dir():
        print(f"✗ Photos directory not found: {photos_dir}")
        sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Load config ──────────────────────────────────────────────────────────
    config = {}
    if args.config:
        config = load_yaml_config(args.config)

    yaml_photos = config.get('photos', {}) or {}

    # CLI args take precedence over YAML, which takes precedence over EXIF
    report_name = args.name or config.get('name')
    location = args.location or config.get('location')
    description = args.description or config.get('description')
    onedrive_path = args.onedrive_path or config.get('onedrive_path')

    print(f"\n📸 Reading photos from: {photos_dir}")
    photos = read_photos_dir(photos_dir, yaml_photos)

    if not photos:
        print("✗ No photos with GPS data found. Nothing to map.")
        sys.exit(1)

    # ── Generate thumbnails ───────────────────────────────────────────────────
    print(f"\n🖼  Generating thumbnails...")
    photos = add_thumbnails(photos)

    # ── OneDrive share links (optional) ──────────────────────────────────────
    if onedrive_path:
        client_id = os.environ.get('ONEDRIVE_CLIENT_ID')
        if not client_id:
            print(f"\n⚠  --onedrive-path set but ONEDRIVE_CLIENT_ID not found in environment.")
            print(f"   Copy .env.example to .env and add your Azure app client ID.")
            print(f"   Continuing without OneDrive share links.\n")
            for photo in photos:
                photo['share_url'] = None
        else:
            print(f"\n🔗 Getting OneDrive share links from: {onedrive_path}")
            from lib.onedrive import add_share_links
            photos = add_share_links(photos, onedrive_path, client_id)
    else:
        for photo in photos:
            photo['share_url'] = None

    # ── Build report metadata ─────────────────────────────────────────────────
    report = build_report_meta(photos, report_name, location, description)

    # ── Render HTML ───────────────────────────────────────────────────────────
    print(f"\n🗺  Rendering map HTML...")
    html_filename = f"{report['slug']}.html"
    html_path = output_dir / html_filename
    render_map(photos, report, html_path)
    print(f"  ✓ Written: {html_path}")

    # ── Deploy to GitHub Pages ───────────────────────────────────────────────
    if args.no_push:
        print(f"\n✅ Done (no-push mode).")
        final_url = html_path.resolve().as_uri()
    else:
        print(f"\n🚀 Deploying to GitHub Pages...")
        final_url = deploy(html_path, report['name'], dry_run=False)
        if not final_url:
            print(f"\n⚠  Deploy failed. HTML saved locally at:")
            final_url = str(html_path.resolve())

    print(f"\n✅ Map ready:")
    print(f"   {final_url}\n")

    if args.open:
        webbrowser.open(str(html_path.resolve()) if args.no_push else final_url)

    return 0


if __name__ == '__main__':
    sys.exit(main())
