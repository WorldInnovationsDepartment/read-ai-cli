"""API client: token management, authenticated requests, pagination."""

import fcntl
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package required. Install: pip install requests")
    sys.exit(1)


# ── Exceptions ─────────────────────────────────────────────────────────

class ReadAIAuthError(Exception):
    """Raised when authentication fails or credentials are missing."""
    pass


class ReadAIAPIError(Exception):
    """Raised when an API request fails."""
    pass


# ── Config ────────────────────────────────────────────────────────────
def _resolve_token_path() -> Path:
    """Resolve token file path with fallback chain:
    1. READAI_TOKEN_FILE env var (explicit override)
    2. ~/.config/readai/tokens.json (XDG standard)
    """
    env_path = os.environ.get("READAI_TOKEN_FILE")
    if env_path:
        return Path(env_path)
    return Path.home() / ".config" / "readai" / "tokens.json"

_token_file_cache: Path | None = None

def get_token_file() -> Path:
    """Lazily resolve and cache the token file path.
    Deferred so that env vars / home dir are read at call time, not import time.
    """
    global _token_file_cache
    if _token_file_cache is None:
        _token_file_cache = _resolve_token_path()
    return _token_file_cache

API_BASE = "https://api.read.ai"
AUTH_BASE = "https://authn.read.ai"
OAUTH_REGISTER_URL = f"{API_BASE}/oauth/register"
OAUTH_UI_URL = f"{API_BASE}/oauth/ui"
TOKEN_URL = f"{AUTH_BASE}/oauth2/token"

SCOPES = "openid email offline_access profile meeting:read mcp:execute"
REDIRECT_URI = f"{API_BASE}/oauth/ui"

# All expandable fields from API Reference
EXPAND_FIELDS = [
    "summary", "chapter_summaries", "action_items",
    "key_questions", "topics", "transcript",
    "metrics", "recording_download",
]


# ── Token Management ──────────────────────────────────────────────────

def load_tokens() -> dict:
    """Load stored OAuth tokens."""
    token_file = get_token_file()
    if token_file.exists():
        return json.loads(token_file.read_text())
    return {}


def save_tokens(tokens: dict):
    """Persist OAuth tokens to disk using atomic write with file locking."""
    token_file = get_token_file()
    token_file.parent.mkdir(parents=True, exist_ok=True)

    # Use file lock to prevent race conditions during token rotation
    lock_path = token_file.parent / ".tokens.lock"
    with open(lock_path, "w") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            existing = {}
            if token_file.exists():
                existing = json.loads(token_file.read_text())
            existing.update(tokens)

            # Atomic write: write to temp file then replace
            fd, tmp_path = tempfile.mkstemp(
                dir=token_file.parent, suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w") as tmp_f:
                    json.dump(existing, tmp_f, indent=2)
                os.chmod(tmp_path, 0o600)
                os.replace(tmp_path, str(token_file))
            except BaseException:
                os.unlink(tmp_path)
                raise
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)


def get_access_token() -> str:
    """Get valid access token, refreshing if needed."""
    tokens = load_tokens()
    if not tokens.get("access_token"):
        raise ReadAIAuthError("Not authenticated. Run: readai auth")

    # Check if token might be expired (tokens expire after 10 min).
    # NOTE: saved_at is recorded locally after the server response arrives,
    # so it may lag behind the server's actual issue time. We use a 60s
    # buffer (instead of e.g. 30s) to be conservative with slow connections.
    saved_at = tokens.get("saved_at", 0)
    expires_in = tokens.get("expires_in", 600)
    now = datetime.now(timezone.utc).timestamp()

    if now - saved_at > expires_in - 60:  # refresh 60s before expiry
        return refresh_access_token(tokens)

    return tokens["access_token"]


def refresh_access_token(tokens: dict) -> str:
    """Refresh the access token using refresh_token.
    NOTE: Refresh token rotation — each refresh returns a NEW refresh token,
    old one is invalidated. File locking in save_tokens() prevents races,
    but avoid running two instances simultaneously for extended periods.
    """
    refresh_token = tokens.get("refresh_token")
    client_id = tokens.get("client_id")
    client_secret = tokens.get("client_secret")

    if not all([refresh_token, client_id, client_secret]):
        raise ReadAIAuthError("Missing credentials. Run: readai auth")

    resp = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        auth=(client_id, client_secret),
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )

    if resp.status_code != 200:
        raise ReadAIAuthError(
            f"Token refresh failed ({resp.status_code}): {resp.text}\n"
            "Try re-authenticating: readai auth"
        )

    data = resp.json()
    data["saved_at"] = datetime.now(timezone.utc).timestamp()
    data["client_id"] = client_id
    data["client_secret"] = client_secret
    save_tokens(data)
    print("✓ Token refreshed", file=sys.stderr)
    return data["access_token"]


def api_request(method: str, path: str, params: dict = None) -> dict:
    """Make an authenticated API request."""
    token = get_access_token()
    url = f"{API_BASE}{path}" if path.startswith("/") else path
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    resp = requests.request(method, url, headers=headers, params=params)

    if resp.status_code == 401:
        # Token expired mid-request, force refresh
        tokens = load_tokens()
        token = refresh_access_token(tokens)
        headers["Authorization"] = f"Bearer {token}"
        resp = requests.request(method, url, headers=headers, params=params)

    if resp.status_code != 200:
        raise ReadAIAPIError(f"API request failed ({resp.status_code}): {resp.text}")

    return resp.json()


def api_list_all(path: str, params: dict = None, max_results: int = None,
                 verbose: bool = False) -> list:
    """Paginate through a list endpoint using cursor-based pagination.
    API limit is max 10 per request. Uses cursor = last item's ID.
    If verbose=True, prints progress to stderr when fetching multiple pages.
    """
    params = dict(params or {})
    params.setdefault("limit", 10)  # API max is 10
    results = []
    page = 1

    while True:
        data = api_request("GET", path, params=params)
        items = data.get("data", [])
        results.extend(items)

        if max_results and len(results) >= max_results:
            results = results[:max_results]
            break

        if not data.get("has_more", False) or not items:
            break

        # cursor = ID of last item in current page
        params["cursor"] = items[-1].get("id")
        page += 1

        if verbose:
            print(f"Fetching meetings... (page {page})", file=sys.stderr)

    return results


def build_expand_params(fields: list[str]) -> dict:
    """Build expand[] query params for the API.
    API uses repeated key: expand[]=summary&expand[]=transcript
    requests library handles list values correctly with this format.
    """
    return {"expand[]": fields}
