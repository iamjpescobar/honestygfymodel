"""
Runs during the Render build (see build command). Downloads the latest
nightly Statcast data package published by GitHub Actions and extracts
it next to this file, producing data/statcast/... for the app engine.

Deliberately NEVER fails the build: if the release doesn't exist yet or
the download hiccups, it prints a warning and exits 0 — the app then
simply falls back to live Statcast pulls, exactly as it works today.

If the GitHub repo is PRIVATE, add a GITHUB_TOKEN environment variable
in Render (a fine-grained personal access token with read access to the
repo's releases). Public repos need nothing.
"""

import io
import json
import os
import sys
import tarfile
import urllib.request

REPO = "iamjpescobar/honestygfymodel"
TAG = "nightly-data"
ASSET = "statcast_data.tar.gz"
DEST = os.path.dirname(os.path.abspath(__file__))  # extracts to app/data/...


def _download_public() -> bytes:
    url = f"https://github.com/{REPO}/releases/download/{TAG}/{ASSET}"
    with urllib.request.urlopen(url, timeout=120) as resp:
        return resp.read()


def _download_with_token(token: str) -> bytes:
    # Private repos: resolve the asset id via the API, then download it.
    api = f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}"
    req = urllib.request.Request(api, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        release = json.loads(resp.read())
    asset_id = next(a["id"] for a in release.get("assets", []) if a["name"] == ASSET)
    dl = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/releases/assets/{asset_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/octet-stream",
        },
    )
    with urllib.request.urlopen(dl, timeout=120) as resp:
        return resp.read()


def main():
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    try:
        blob = _download_with_token(token) if token else _download_public()
    except Exception as exc:
        print(f"[fetch_data] WARNING: could not download nightly data ({exc}). "
              f"App will fall back to live Statcast pulls.")
        return 0

    try:
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
            tar.extractall(DEST)
        manifest_path = os.path.join(DEST, "data", "statcast", "manifest.json")
        if os.path.exists(manifest_path):
            with open(manifest_path) as f:
                m = json.load(f)
            print(f"[fetch_data] OK: real Statcast data through {m.get('through_date')} "
                  f"({m.get('total_pitches'):,} pitches, "
                  f"{m.get('n_batters')} batters / {m.get('n_pitchers')} pitchers), "
                  f"fetched {m.get('generated_at_utc')}")
        else:
            print("[fetch_data] Extracted, but no manifest found — check archive contents.")
    except Exception as exc:
        print(f"[fetch_data] WARNING: extraction failed ({exc}). "
              f"App will fall back to live Statcast pulls.")
    return 0


if __name__ == "__main__":
    sys.exit(main())