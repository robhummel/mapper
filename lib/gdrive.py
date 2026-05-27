"""
Google Drive integration for uploading photos and generating share links.

Auth: OAuth 2.0 Desktop app flow (user logs in once via browser;
      token cached to ~/.mapper-gdrive-token.json).

Credentials JSON file is downloaded from Google Cloud Console and
pointed to via GOOGLE_CREDENTIALS_FILE in .env.

Scope used: drive.file — only allows access to files this app creates,
            which is the minimum permission needed.
"""

from pathlib import Path
from typing import Optional

TOKEN_CACHE_PATH = Path.home() / '.mapper-gdrive-token.json'
SCOPES = ['https://www.googleapis.com/auth/drive.file']

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    GDRIVE_AVAILABLE = True
except ImportError:
    GDRIVE_AVAILABLE = False


def _authenticate(credentials_file: str):
    """
    Authenticate with Google Drive via OAuth 2.0 Desktop app flow.
    Returns a Drive API service object, or None on failure.
    """
    if not GDRIVE_AVAILABLE:
        print("  ⚠ Google API libraries not installed.")
        print("    Run: uv pip install google-api-python-client google-auth-oauthlib google-auth-httplib2")
        return None

    creds = None

    if TOKEN_CACHE_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_CACHE_PATH), SCOPES)
        except Exception:
            pass

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None  # Force re-auth if refresh fails

        if not creds or not creds.valid:
            print(f"\n  Google Drive authentication required.")
            print(f"  Your browser will open — sign in and grant access.\n")
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0, open_browser=True)

        TOKEN_CACHE_PATH.write_text(creds.to_json())
        TOKEN_CACHE_PATH.chmod(0o600)

    print("  ✓ Google Drive authenticated")
    return build('drive', 'v3', credentials=creds, cache_discovery=False)


def _create_folder(service, folder_name: str) -> str:
    """Create a folder in Drive root and return its ID."""
    # Check if folder already exists (idempotent re-runs)
    results = service.files().list(
        q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id, name)",
    ).execute()

    existing = results.get('files', [])
    if existing:
        folder_id = existing[0]['id']
        print(f"  ℹ Using existing Drive folder: {folder_name}")
        return folder_id

    folder_meta = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
    }
    folder = service.files().create(body=folder_meta, fields='id').execute()
    print(f"  ✓ Created Drive folder: {folder_name}")
    return folder['id']


def _upload_file(service, local_path: str, folder_id: str, filename: str) -> Optional[str]:
    """
    Upload a file to a Drive folder.
    Returns the file ID, or None on failure.
    """
    # Check if already uploaded (idempotent re-runs)
    results = service.files().list(
        q=f"name='{filename}' and '{folder_id}' in parents and trashed=false",
        fields="files(id, name)",
    ).execute()
    existing = results.get('files', [])
    if existing:
        return existing[0]['id']

    file_meta = {'name': filename, 'parents': [folder_id]}
    media = MediaFileUpload(local_path, resumable=True)
    uploaded = service.files().create(
        body=file_meta,
        media_body=media,
        fields='id',
    ).execute()
    return uploaded.get('id')


def _make_public(service, file_id: str) -> None:
    """Set a file to be readable by anyone with the link."""
    service.permissions().create(
        fileId=file_id,
        body={'type': 'anyone', 'role': 'reader'},
    ).execute()


def _share_url(file_id: str) -> str:
    """Return the standard Google Drive shareable view URL."""
    return f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"


def upload_and_share(
    photos: list[dict],
    folder_name: str,
    credentials_file: str,
) -> list[dict]:
    """
    Upload photos to a Google Drive folder and add share URLs to each dict.

    Args:
        photos:           List of photo metadata dicts (must have 'path' and 'filename').
        folder_name:      Name of the Drive folder to create (or reuse).
        credentials_file: Path to the OAuth 2.0 client credentials JSON from Google Cloud.

    Returns:
        Same list, with 'share_url' added to each dict.
    """
    print(f"  Connecting to Google Drive...")
    service = _authenticate(credentials_file)
    if not service:
        print("  ⚠ Skipping Google Drive upload.")
        for photo in photos:
            photo['share_url'] = None
        return photos

    folder_id = _create_folder(service, folder_name)

    total = len(photos)
    uploaded = 0
    for i, photo in enumerate(photos, start=1):
        print(f"  Uploading {i}/{total}: {photo['filename']}", end='\r')
        try:
            file_id = _upload_file(service, photo['path'], folder_id, photo['filename'])
            if file_id:
                _make_public(service, file_id)
                photo['share_url'] = _share_url(file_id)
                uploaded += 1
            else:
                photo['share_url'] = None
        except Exception as e:
            print(f"\n  ⚠ Failed to upload {photo['filename']}: {e}")
            photo['share_url'] = None

    print(f"  ✓ {uploaded}/{total} photo(s) uploaded to Drive folder '{folder_name}'")
    return photos
