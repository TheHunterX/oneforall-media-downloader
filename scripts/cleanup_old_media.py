import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

REPO = os.environ.get("GITHUB_REPOSITORY", "TheHunterX/oneforall-media-downloader")
TOKEN = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()

def gh_api(path: str, method: str = "GET"):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "OneForAll-MediaCleaner"
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(f"https://api.github.com{path}", headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw.strip() else {}

def parse_iso_utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))

def cleanup(max_age_hours: float = 24.0):
    if not TOKEN:
        print("[MediaCleaner] Missing GITHUB_TOKEN / GH_TOKEN. Exiting.")
        sys.exit(1)

    now = datetime.now(timezone.utc)
    max_age_sec = max_age_hours * 3600.0
    print(f"[MediaCleaner] Pruning repo '{REPO}' for media older than {max_age_hours}h...")

    # 1. Prune Release Assets on v1.0-media
    deleted_assets = 0
    kept_assets = 0
    try:
        rel = gh_api(f"/repos/{REPO}/releases/tags/v1.0-media")
        rel_id = rel.get("id")
        if rel_id:
            page = 1
            to_delete = []
            while True:
                assets = gh_api(f"/repos/{REPO}/releases/{rel_id}/assets?per_page=100&page={page}")
                if not assets:
                    break
                for a in assets:
                    ts_str = a.get("updated_at") or a.get("created_at") or ""
                    age_sec = (now - parse_iso_utc(ts_str)).total_seconds() if ts_str else (max_age_sec + 1)
                    if max_age_hours <= 0 or age_sec >= max_age_sec:
                        to_delete.append((a["id"], a.get("name", "?"), round(age_sec / 3600, 1)))
                    else:
                        kept_assets += 1
                if len(assets) < 100:
                    break
                page += 1

            for aid, aname, age_h in to_delete:
                try:
                    gh_api(f"/repos/{REPO}/releases/assets/{aid}", method="DELETE")
                    deleted_assets += 1
                    print(f"  [Deleted Asset] {aname} (age={age_h}h)")
                except Exception as de:
                    print(f"  [Warn Asset] Could not delete {aname} ({aid}): {de}")
    except urllib.error.HTTPError as he:
        if he.code == 404:
            print("[MediaCleaner] Release v1.0-media does not exist yet.")
        else:
            print(f"[MediaCleaner] Release check HTTP {he.code}: {he}")
    except Exception as e:
        print(f"[MediaCleaner] Release cleanup error: {e}")

    # 2. Prune GitHub Actions Artifacts older than max_age_hours
    deleted_artifacts = 0
    kept_artifacts = 0
    try:
        page = 1
        art_to_delete = []
        while True:
            data = gh_api(f"/repos/{REPO}/actions/artifacts?per_page=100&page={page}")
            arts = data.get("artifacts") or []
            if not arts:
                break
            for art in arts:
                if art.get("expired"):
                    continue
                ts_str = art.get("updated_at") or art.get("created_at") or ""
                age_sec = (now - parse_iso_utc(ts_str)).total_seconds() if ts_str else (max_age_sec + 1)
                if max_age_hours <= 0 or age_sec >= max_age_sec:
                    art_to_delete.append((art["id"], art.get("name", "?"), round(age_sec / 3600, 1)))
                else:
                    kept_artifacts += 1
            if len(arts) < 100:
                break
            page += 1

        for art_id, art_name, age_h in art_to_delete:
            try:
                gh_api(f"/repos/{REPO}/actions/artifacts/{art_id}", method="DELETE")
                deleted_artifacts += 1
                print(f"  [Deleted Artifact] #{art_id} ({art_name}, age={age_h}h)")
            except Exception as ade:
                print(f"  [Warn Artifact] Could not delete #{art_id}: {ade}")
    except Exception as ae:
        print(f"[MediaCleaner] Artifact cleanup note: {ae}")

    print(f"[MediaCleaner] Done! Deleted {deleted_assets} release assets (kept {kept_assets}) & deleted {deleted_artifacts} artifacts (kept {kept_artifacts}).")

if __name__ == "__main__":
    hours = float(sys.argv[1]) if len(sys.argv) > 1 else 24.0
    cleanup(hours)
