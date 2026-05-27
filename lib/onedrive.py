"""
Microsoft OneDrive integration via Microsoft Graph API.

Authenticates with MSAL device code flow (user logs in once; token cached).
Creates anonymous view share links for photos so they can be embedded in the map.
"""

import json
import os
from pathlib import Path
from typing import Optional

import requests

try:
    import msal
    MSAL_AVAILABLE = True
except ImportError:
    MSAL_AVAILABLE = False

GRAPH_API = 'https://graph.microsoft.com/v1.0'
SCOPES = ['Files.ReadWrite', 'offline_access']
TOKEN_CACHE_PATH = Path.home() / '.mapper-token.json'
AUTHORITY = 'https://login.microsoftonline.com/common'


def _get_client_id() -> Optional[str]:
    """Get OneDrive client ID from environment."""
    return os.environ.get('ONEDRIVE_CLIENT_ID')


def _load_token_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if TOKEN_CACHE_PATH.exists():
        cache.deserialize(TOKEN_CACHE_PATH.read_text())
    return cache


def _save_token_cache(cache: msal.SerializableTokenCache) -> None:
    if cache.has_state_changed:
        TOKEN_CACHE_PATH.write_text(cache.serialize())
        TOKEN_CACHE_PATH.chmod(0o600)


def _get_app(client_id: str) -> msal.PublicClientApplication:
    cache = _load_token_cache()
    return msal.PublicClientApplication(
        client_id,
        authority=AUTHORITY,
        token_cache=cache,
    )


def authenticate(client_id: str) -> Optional[str]:
    """
    Authenticate with OneDrive via device code flow.

    Returns an access token string, or None on failure.
    """
    if not MSAL_AVAILABLE:
        print("  ⚠ msal not installed — skipping OneDrive integration")
        return None

    app = _get_app(client_id)

    # Try silent auth first (cached token)
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and 'access_token' in result:
            _save_token_cache(app.token_cache)
            return result['access_token']

    # Fall back to device code flow
    flow = app.initiate_device_flow(scopes=SCOPES)
    if 'user_code' not in flow:
        print(f"  ✗ Could not start device flow: {flow.get('error_description', 'unknown error')}")
        return None

    print(f"\n  OneDrive authentication required.")
    print(f"  Visit: {flow['verification_uri']}")
    print(f"  Enter code: {flow['user_code']}\n")

    result = app.acquire_token_by_device_flow(flow)
    if 'access_token' not in result:
        print(f"  ✗ Authentication failed: {result.get('error_description', 'unknown')}")
        return None

    _save_token_cache(app.token_cache)
    print("  ✓ OneDrive authenticated")
    return result['access_token']


def _graph_get(token: str, endpoint: str) -> Optional[dict]:
    """Make a GET request to the Graph API."""
    resp = requests.get(
        f"{GRAPH_API}{endpoint}",
        headers={'Authorization': f'Bearer {token}'},
        timeout=15,
    )
    if resp.status_code == 200:
        return resp.json()
    return None


def _graph_post(token: str, endpoint: str, body: dict) -> Optional[dict]:
    """Make a POST request to the Graph API."""
    resp = requests.post(
        f"{GRAPH_API}{endpoint}",
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        },
        json=body,
        timeout=15,
    )
    if resp.status_code in (200, 201):
        return resp.json()
    return None


def get_share_link(token: str, onedrive_path: str, filename: str) -> Optional[str]:
    """
    Get an anonymous view share link for a file in OneDrive.

    Args:
        token: Graph API access token.
        onedrive_path: Path to the folder in OneDrive (relative to root), e.g. "Hikes/Trail1".
        filename: The filename, e.g. "IMG_001.jpg".

    Returns:
        A public share URL string, or None if the file was not found.
    """
    # Normalise path
    folder = onedrive_path.strip('/')
    file_path = f"/{folder}/{filename}" if folder else f"/{filename}"

    # Find the item
    item = _graph_get(token, f"/me/drive/root:{file_path}")
    if not item:
        print(f"    ⚠ Not found in OneDrive: {file_path}")
        return None

    item_id = item['id']

    # Create (or retrieve existing) anonymous view link
    result = _graph_post(
        token,
        f"/me/drive/items/{item_id}/createLink",
        {"type": "view", "scope": "anonymous"},
    )
    if result and 'link' in result:
        return result['link']['webUrl']

    print(f"    ⚠ Could not create share link for: {filename}")
    return None


def add_share_links(
    photos: list[dict],
    onedrive_path: str,
    client_id: str,
) -> list[dict]:
    """
    Add OneDrive share links to each photo dict.

    Args:
        photos: List of photo metadata dicts.
        onedrive_path: OneDrive folder path (relative to root).
        client_id: Azure app client ID.

    Returns:
        Same list, with 'share_url' added where available.
    """
    print(f"  Connecting to OneDrive...")
    token = authenticate(client_id)
    if not token:
        print("  ⚠ Skipping OneDrive share links.")
        for photo in photos:
            photo['share_url'] = None
        return photos

    total = len(photos)
    linked = 0
    for i, photo in enumerate(photos, start=1):
        print(f"  Getting share link {i}/{total}: {photo['filename']}", end='\r')
        url = get_share_link(token, onedrive_path, photo['filename'])
        photo['share_url'] = url
        if url:
            linked += 1

    print(f"  ✓ {linked}/{total} share link(s) created                    ")
    return photos
