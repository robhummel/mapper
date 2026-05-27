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
| `--onedrive-path PATH` | OneDrive folder for share links (e.g. `Hikes/Trail1`) |
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

## OneDrive Integration (Optional)

Share links let the trail manager tap "View full image" to open the original photo on OneDrive.

1. Register an app at [portal.azure.com](https://portal.azure.com) → Azure Active Directory → App registrations
2. Add redirect URI: `https://login.microsoftonline.com/common/oauth2/nativeclient`
3. Grant delegated permission: `Files.ReadWrite`
4. Copy your client ID to `.env`:
   ```
   ONEDRIVE_CLIENT_ID=your-client-id-here
   ```
5. Run with `--onedrive-path "Hikes/YourFolder"` — you'll be prompted to log in once; the token is cached.

## One-Time GitHub Pages Setup

```bash
gh api repos/robhummel/mapper/pages \
  -X POST \
  -f source[branch]=main \
  -f source[path]=/output
```

Maps publish to: `https://robhummel.github.io/mapper/REPORT-NAME.html`

## Photo Requirements

- GPS coordinates must be embedded in EXIF (standard for iPhone and most Android cameras)
- Supported formats: JPEG, HEIC, PNG, TIFF
- Photos without GPS are skipped with a warning (add `lat`/`lon` in YAML to include them)
- Notes are read from `UserComment`, `ImageDescription`, or `XPComment` EXIF fields
