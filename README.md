# 🗺 Trail Hazard Mapper

Generates a mobile-friendly interactive map from GPS-tagged hike photos and publishes it to GitHub Pages. Trail managers receive a single link — they can view hazard markers on the map, tap each one to see the photo and notes, and follow their live GPS position as they walk the trail.

## Features

- 📍 **Live GPS position** — pulsing blue dot tracks the viewer as they walk
- 🔢 **Numbered hazard markers** in chronological order
- 🖼 **Photo popups** — thumbnail + timestamp + notes on marker tap
- 🔎 **Lightbox** — tap thumbnail for full-screen photo view
- 🔗 **OneDrive links** — optional "View full image" link to original photo
- 📱 **Mobile-first** — touch-optimised, works in Safari and Chrome with no app install
- 🚀 **GitHub Pages deploy** — one command → shareable URL

## Quick Start

```bash
# 1. Clone and set up
git clone https://github.com/robhummel/mapper
cd mapper
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# 2. Generate a map (no push, opens locally)
python mapper.py \
  --photos /path/to/hike/photos \
  --name "Central Trail Report" \
  --location "Hopkinton, MA" \
  --no-push --open

# 3. Generate and publish to GitHub Pages
python mapper.py \
  --photos /path/to/hike/photos \
  --config hike.yaml \
  --onedrive-path "Hikes/CentralTrail-2026-05-26"
```

## Options

| Flag | Description |
|------|-------------|
| `--photos PATH` | Directory of GPS-tagged photos **(required)** |
| `--config FILE` | YAML config file (see `example.yaml`) |
| `--name TEXT` | Report name (overrides YAML) |
| `--location TEXT` | Location label shown in header |
| `--description TEXT` | Description shown in header |
| `--gdrive-folder NAME` | Upload photos to this Google Drive folder and embed share links |
| `--no-push` | Generate HTML locally without pushing to GitHub Pages |
| `--open` | Open the generated HTML in your browser |
| `--output-dir DIR` | Output directory (default: `./output`) |

## YAML Config

```yaml
name: "Central Trail Hazard Report"
location: "Hopkinton, MA"
description: "Trail hazard inspection — Spring 2026"

photos:
  "IMG_001.jpg":
    notes: "Poison ivy patch on right side of trail"
  "IMG_002.jpg":
    notes: "Large fallen oak blocking path"
    # Manual coordinates if photo lacks GPS:
    # lat: 42.2345
    # lon: -71.5123
```

Notes in the YAML **override** any notes embedded in the photo's EXIF.  
If a photo has notes in EXIF (`UserComment` / `ImageDescription`) and no YAML override, the EXIF notes are used.

## Google Drive Integration (Optional)

Uploads photos to Google Drive and adds a "View full image →" link in each marker popup.

1. Go to **[console.cloud.google.com](https://console.cloud.google.com)** → Create or select a project
2. Enable the **Google Drive API**
3. Go to **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**
   - Application type: **Desktop app** → Create → **Download JSON**
4. Add the path to that JSON file in `.env`:
   ```
   GOOGLE_CREDENTIALS_FILE=/path/to/client_secret_xxxx.json
   ```
5. Run with `--gdrive-folder "CentralTrail-2026-05-26"` — your browser opens once for sign-in; token is cached at `~/.mapper-gdrive-token.json`.

Photos are uploaded to a new folder in your Google Drive root (reused on re-runs). Each photo is made publicly readable via "anyone with link".

## One-Time GitHub Pages Setup

```bash
gh api repos/robhummel/mapper/pages \
  --method POST \
  --field 'source[branch]=main' \
  --field 'source[path]=/docs'
```

Maps publish to: `https://robhummel.github.io/mapper/REPORT-NAME.html`

## Photo Requirements

- GPS coordinates must be embedded in EXIF (standard for iPhone and most Android cameras)
- Supported formats: JPEG, HEIC, PNG, TIFF
- Photos without GPS are skipped with a warning (add `lat`/`lon` in YAML to include them)
- Notes are read from `UserComment`, `ImageDescription`, or `XPComment` EXIF fields
