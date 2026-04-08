"""OAuth authentication: client registration and token exchange."""

import base64
import json
import re
import sys
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package required. Install: pip install requests")
    sys.exit(1)

from .api import (
    get_token_file, OAUTH_REGISTER_URL, OAUTH_UI_URL, TOKEN_URL,
    SCOPES, REDIRECT_URI, load_tokens, save_tokens,
)


def parse_curl_command(curl_str: str) -> dict:
    """Parse a curl command from Read AI OAuth UI into its components.
    Extracts: client_id, client_secret (from Basic auth), and all -d fields.
    """
    result = {}

    # Extract Basic auth → client_id:client_secret
    # Pattern: "Authorization: Basic $(echo -n 'ID:SECRET' | base64)"
    # Supports both single-quoted and double-quoted variants
    basic_match = re.search(r"""echo\s+-n\s+['"]([^'"]+)['"]\s*\|\s*base64""", curl_str)
    if basic_match:
        creds = basic_match.group(1)
        if ":" in creds:
            result["client_id"], result["client_secret"] = creds.split(":", 1)
    else:
        # Try already-encoded Basic header
        basic_b64 = re.search(r'Basic\s+([A-Za-z0-9+/=]+)', curl_str)
        if basic_b64:
            try:
                decoded = base64.b64decode(basic_b64.group(1)).decode()
                if ":" in decoded:
                    result["client_id"], result["client_secret"] = decoded.split(":", 1)
            except Exception:
                pass

    # Extract all -d / --data / --data-urlencode "key=value" or 'key=value' fields
    for match in re.finditer(
        r'(?:-d|--data(?:-urlencode)?)\s+["\']([^"\']+)["\']', curl_str
    ):
        field = match.group(1)
        if "=" in field:
            key, val = field.split("=", 1)
            result[key] = val

    # Extract URL
    url_match = re.search(r'(https://\S+/oauth2/token)', curl_str)
    if url_match:
        result["token_url"] = url_match.group(1)

    return result


def cmd_auth(args):
    """OAuth authentication — paste the curl command from Read AI OAuth UI."""
    tokens = load_tokens()

    # If --register flag, do client registration first
    if getattr(args, "register", False) or not tokens.get("client_id"):
        print("=== Step 1: Register OAuth Client ===")

        if tokens.get("client_id"):
            print(f"  Existing client: {tokens['client_id']}")
            answer = input("  Re-register? (y/N): ").strip().lower()
            if answer != "y":
                print(f"  Using existing client.")
            else:
                tokens = {}

        if not tokens.get("client_id"):
            print("  Registering new OAuth client with Read AI...")
            resp = requests.post(
                OAUTH_REGISTER_URL,
                headers={"Content-Type": "application/json"},
                json={
                    "client_name": "Read AI CLI",
                    "redirect_uris": [REDIRECT_URI],
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                    "scope": SCOPES,
                    "token_endpoint_auth_method": "client_secret_basic",
                },
            )

            if resp.status_code not in (200, 201):
                print(f"  ERROR: Registration failed ({resp.status_code}): {resp.text}")
                sys.exit(1)

            data = resp.json()
            client_id = data.get("client_id")
            client_secret = data.get("client_secret")

            if not client_id or not client_secret:
                print(f"  ERROR: Unexpected response: {json.dumps(data, indent=2)}")
                sys.exit(1)

            save_tokens({"client_id": client_id, "client_secret": client_secret})
            print(f"  ✓ Client registered: {client_id}")

    tokens = load_tokens()
    client_id = tokens.get("client_id", "")
    client_secret = tokens.get("client_secret", "")

    print()
    print("=== OAuth Flow ===")
    print()
    print("1. Open in your browser: " + OAUTH_UI_URL)
    if client_id:
        print(f"   Client ID:     {client_id}")
        print(f"   Client Secret: {client_secret}")
    print()
    print("2. Complete the OAuth flow in the browser")
    print("3. Click 'Copy Command' on the success page")
    print("4. Paste the FULL curl command below:")
    print()

    # Read curl command (may be multi-line with backslashes)
    lines = []
    print("curl command> ", end="", flush=True)
    while True:
        line = input().rstrip()
        lines.append(line)
        if not line.endswith("\\"):
            break
    curl_cmd = " ".join(l.rstrip("\\").strip() for l in lines)

    if not curl_cmd.strip():
        print("ERROR: No curl command provided.")
        sys.exit(1)

    # Parse the curl command
    parsed = parse_curl_command(curl_cmd)

    p_client_id = parsed.get("client_id", client_id)
    p_client_secret = parsed.get("client_secret", client_secret)
    auth_code = parsed.get("code", "")
    code_verifier = parsed.get("code_verifier", "")
    redirect_uri = parsed.get("redirect_uri", REDIRECT_URI)
    token_url = parsed.get("token_url", TOKEN_URL)

    if not auth_code:
        print("ERROR: Could not extract authorization code from curl command.")
        print(f"  Parsed fields: {list(parsed.keys())}")
        sys.exit(1)

    if not p_client_id or not p_client_secret:
        print("ERROR: Could not extract client credentials from curl command.")
        sys.exit(1)

    # Save client creds if new
    if p_client_id != client_id or p_client_secret != client_secret:
        save_tokens({"client_id": p_client_id, "client_secret": p_client_secret})

    print()
    print("=== Exchanging Code for Tokens ===")

    post_data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": redirect_uri,
    }
    if code_verifier:
        post_data["code_verifier"] = code_verifier

    resp = requests.post(
        token_url,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        auth=(p_client_id, p_client_secret),
        data=post_data,
    )

    if resp.status_code != 200:
        print(f"ERROR: Token exchange failed ({resp.status_code}): {resp.text}")
        sys.exit(1)

    data = resp.json()
    data["saved_at"] = datetime.now(timezone.utc).timestamp()
    data["client_id"] = p_client_id
    data["client_secret"] = p_client_secret
    save_tokens(data)

    print("✓ Authentication complete! Tokens saved.")
    print(f"  Token file: {get_token_file()}")
    print(f"  Access token expires in: {data.get('expires_in', '?')}s")
    print(f"  Scopes: {data.get('scope', '?')}")
