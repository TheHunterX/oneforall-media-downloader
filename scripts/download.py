import os
import sys
import re
import time
import json
import math
import shutil
import base64
import queue
import random
import secrets
import tempfile
import threading
import urllib.request
import urllib.parse
import subprocess
from pathlib import Path
from typing import Optional

try:
    from curl_cffi import requests as cf_requests
except Exception:
    cf_requests = None

GENERIC_CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"

def get_ytdlp_cmd() -> list:
    base = ["yt-dlp"] if shutil.which("yt-dlp") else [sys.executable, "-m", "yt_dlp"]
    if shutil.which("node"):
        base.extend(["--js-runtimes", "node", "--remote-components", "ejs:github"])
    return base

def write_state(status: str, percent: int = 0, text: str = "", remaining: int = 0):
    state_file = os.environ.get("DL_STATE_FILE", "/tmp/dl_state.json")
    try:
        data = {"status": status, "percent": percent, "text": text, "remaining": remaining}
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass

def set_error_reason(code: str, detail: str):
    """Record a specific Cobalt-style error reason (private, age, unavailable) for user notification."""
    try:
        err_file = os.environ.get("DL_ERROR_FILE", "/tmp/dl_error_reason.txt")
        Path(err_file).write_text(f"{code}|{detail}", encoding="utf-8")
    except Exception:
        pass

def report_progress(percent: int, status_text: str, remaining: int = 0):
    write_state("progress", percent, status_text, remaining)
    log(f"Live Progress state: {percent}% - {status_text}")

def log(msg: str):
    print(f"[OneForAllDownloader] {msg}", flush=True)

def _find_master_cookies_file() -> Optional[Path]:
    candidates = [
        Path("cookies.txt"),
        Path("/tmp/cookies.txt"),
        Path(os.environ.get("COOKIES_FILE", "")) if os.environ.get("COOKIES_FILE") else None,
    ]
    for c in candidates:
        if c and c.exists() and c.is_file() and c.stat().st_size > 50:
            return c
    return None

def get_cookie_args(for_url: str = "", allow_instagram: bool = False) -> list:
    """Return a fresh temp copy of cookies.txt so yt-dlp never corrupts/overwrites the master cookie file."""
    low = (for_url or "").lower()
    is_yt = ("youtube.com" in low or "youtu.be" in low)
    is_ig = ("instagram.com" in low or "ddinstagram.com" in low)
    if for_url and not (is_yt or (allow_instagram and is_ig)):
        return []
    master = _find_master_cookies_file()
    if not master:
        return []
    try:
        tmp_copy = Path(tempfile.gettempdir()) / f"ofah_cookies_{os.getpid()}_{int(time.time()*1000)}_{random.randint(100,999)}.txt"
        shutil.copy2(master, tmp_copy)
        log(f"Prepared isolated cookies copy from {master} ({master.stat().st_size} bytes)")
        return ["--cookies", str(tmp_copy)]
    except Exception as e:
        log(f"Cookie copy note: {e}")
        return ["--cookies", str(master)]

def load_domain_cookies(domain_keywords: list) -> tuple[str, dict]:
    """Parse Netscape cookies.txt into (cookie_header_str, cookie_dict) for specified domains."""
    master = _find_master_cookies_file()
    if not master:
        return "", {}
    cookie_dict = {}
    try:
        for line in master.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            cols = line.split("\t")
            if len(cols) >= 7:
                dom = cols[0].lower()
                if any(k in dom for k in domain_keywords):
                    cookie_dict[cols[5]] = cols[6]
    except Exception as e:
        log(f"Cookie parse note: {e}")
    header_str = "; ".join(f"{k}={v}" for k, v in cookie_dict.items())
    return header_str, cookie_dict

def resolve_redirect_url(url: str) -> str:
    """Follow redirects using Cobalt-proven headers (e.g. curl UA for Instagram /share/, official Pinterest shortener API, TikTok HTML redirects)."""
    url = url.strip()
    url_l = url.lower()

    # 1. Cobalt trick: Instagram /share/ links return HTML on browser UA, so request with curl/7.88.1!
    if ("instagram.com/share/" in url_l or "ddinstagram.com/share/" in url_l):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/7.88.1"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                resolved = resp.geturl()
                if resolved and resolved != url:
                    log(f"Unshortened Instagram share link: {url} -> {resolved}")
                    return resolved
        except Exception as e:
            log(f"Instagram share unshorten note: {e}")

    # 2. Cobalt Pinterest shortener API (pin.it/<code>)
    pin_short = re.search(r'https?://(?:www\.)?pin\.it/([a-zA-Z0-9_-]+)', url)
    if pin_short:
        code = pin_short.group(1)
        try:
            api_redir = f"https://api.pinterest.com/url_shortener/{code}/redirect/"
            req = urllib.request.Request(api_redir, headers={"User-Agent": GENERIC_CHROME_UA})
            with urllib.request.urlopen(req, timeout=10) as resp:
                resolved = resp.geturl()
                if resolved and resolved != api_redir:
                    log(f"Unshortened Pinterest pin.it: {url} -> {resolved}")
                    return resolved
        except Exception as e:
            log(f"Pinterest pin.it redirect note: {e}")

    # 3. Facebook /share/ & fb.watch redirects
    if any(k in url_l for k in ["fb.watch/", "facebook.com/share/", "m.facebook.com/share/"]):
        try:
            if cf_requests:
                r = cf_requests.get(url, impersonate="chrome", headers={
                    "User-Agent": GENERIC_CHROME_UA,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                }, allow_redirects=True, timeout=12)
                if r.url and r.url != url:
                    log(f"Unshortened Facebook link: {url} -> {r.url}")
                    return r.url
        except Exception as e:
            log(f"Facebook unshorten note: {e}")

    # 4. TikTok short links (vt.tiktok.com, vm.tiktok.com, tiktok.com/t/) + Spotify (spotify.link, spoti.fi) + Reddit /s/ + v.redd.it + t.co + youtu.be + bit.ly
    if any(short in url_l for short in ["vt.tiktok.com", "vm.tiktok.com", "tiktok.com/t/", "spotify.link", "spoti.fi", "pin.it", "t.co", "youtu.be", "bit.ly", "v.redd.it", "/s/"]):
        try:
            ua = GENERIC_CHROME_UA.split(" Chrome/1")[0] if "tiktok.com" in url_l else GENERIC_CHROME_UA
            req = urllib.request.Request(url, headers={"User-Agent": ua})
            with urllib.request.urlopen(req, timeout=10) as resp:
                resolved = resp.geturl()
                if resolved and resolved != url:
                    log(f"Unshortened URL: {url} -> {resolved}")
                    return resolved
                # Cobalt TikTok fallback: handle `<a href="https://...">` HTML redirect body
                if "tiktok.com" in url_l:
                    body = resp.read(2048).decode("utf-8", errors="ignore")
                    m_href = re.search(r'<a\s+href="(https://[^"]+)"', body)
                    if m_href:
                        resolved2 = m_href.group(1).split("?")[0]
                        log(f"Unshortened TikTok HTML href: {url} -> {resolved2}")
                        return resolved2
        except Exception as e:
            log(f"URL unshortening note ({url}): {e}")
    return url

def sanitize_url(raw_url: str) -> str:
    """Clean and normalize media URLs (Cobalt-style normalization), stripping playlists, trackers, and session params."""
    raw_url = raw_url.strip()
    # Normalize alt domains (Cobalt url.js)
    raw_url = re.sub(r'^https?://(?:[dg]\.)?ddinstagram\.com/', 'https://www.instagram.com/', raw_url, flags=re.IGNORECASE)
    raw_url = re.sub(r'^https?://(?:www\.)?(?:vxtwitter|fixvx|fxtwitter)\.com/', 'https://x.com/', raw_url, flags=re.IGNORECASE)
    raw_url = resolve_redirect_url(raw_url)

    # 1. YouTube: Extract pure 11-char video ID (including /live/, /shorts/, /embed/, youtu.be)
    if "youtube.com" in raw_url or "youtu.be" in raw_url:
        match = re.search(r'(?:v=|/shorts/|/live/|/embed/|youtu\.be/|/v/)([a-zA-Z0-9_-]{8,15})', raw_url)
        if match:
            clean_id = match.group(1)
            log(f"Sanitized YouTube URL to pure video: {clean_id}")
            return f"https://www.youtube.com/watch?v={clean_id}"

    # 2. Instagram: Strip ?igsh= trackers, support /reel/, /reels/, /p/, /tv/, /stories/user/id/, /user/reel/id/
    if "instagram.com" in raw_url:
        clean = raw_url.split("?")[0].split("#")[0].rstrip("/")
        return clean + "/"

    # 3. TikTok: Strip tracking params
    if "tiktok.com" in raw_url:
        return raw_url.split("?")[0]

    # 4. Twitter / X: Normalize
    if "twitter.com" in raw_url or "x.com" in raw_url:
        return raw_url.split("?")[0]

    # 5. Pinterest: Strip query trackers & localize host
    if "pinterest." in raw_url:
        clean = raw_url.split("?")[0]
        clean = re.sub(r'^https?://[a-z0-9-]+\.pinterest\.[a-z.]+/', 'https://www.pinterest.com/', clean, flags=re.IGNORECASE)
        return clean

    # 6. Facebook: Normalize watch?v= and strip junk trackers
    if "facebook.com" in raw_url or "fb.watch" in raw_url:
        v_param = re.search(r'[?&]v=([0-9]+)', raw_url)
        if v_param:
            return f"https://www.facebook.com/reel/{v_param.group(1)}"
        return raw_url.split("?")[0]

    # 7. Reddit: Strip query trackers
    if "reddit.com" in raw_url:
        return raw_url.split("?")[0]

    # 8. Spotify: Strip /intl-xx/ locale segment and ?si= query trackers
    if "spotify.com" in raw_url:
        clean = raw_url.split("?")[0].split("#")[0]
        clean = re.sub(r'open\.spotify\.com/intl-[a-z-]+/', 'open.spotify.com/', clean, flags=re.IGNORECASE)
        return clean

    return raw_url

def extract_media_id(url: str) -> str:
    """Extract a safe identifier for deterministic file naming."""
    sp_m = re.search(r'spotify\.com/(?:intl-[a-z-]+/)?(?:track|album|playlist|episode)/([a-zA-Z0-9]+)', url)
    if sp_m:
        return f"sp_{sp_m.group(1)}"
    yt_m = re.search(r'(?:v=|/shorts/|/live/|/embed/|youtu\.be/|/v/)([a-zA-Z0-9_-]{8,15})', url)
    if yt_m:
        return yt_m.group(1)
    ig_story = re.search(r'/stories/[^/]+/([0-9]+)', url)
    if ig_story:
        return f"story_{ig_story.group(1)}"
    ig_m = re.search(r'/(?:reels?|p|tv)/([a-zA-Z0-9_-]+)', url)
    if ig_m:
        return ig_m.group(1)
    tk_m = re.search(r'/(?:video|photo)/([0-9]+)', url)
    if tk_m:
        return tk_m.group(1)
    tw_m = re.search(r'status/([0-9]+)', url)
    if tw_m:
        return tw_m.group(1)
    pin_m = re.search(r'/pin/(?:[^/]+--)?([0-9]+)', url)
    if pin_m:
        return pin_m.group(1)
    fb_m = re.search(r'/(?:reel|videos)/([0-9]+)', url)
    if fb_m:
        return f"fb_{fb_m.group(1)}"
    rd_m = re.search(r'/comments/([a-zA-Z0-9]+)', url)
    if rd_m:
        return f"rd_{rd_m.group(1)}"
    return "".join(c for c in url.rstrip("/").split("/")[-1] if c.isalnum() or c in ("-", "_"))[:20] or "media"

def check_warp_proxy() -> Optional[str]:
    """Check if the local Cloudflare WARP proxy (wireproxy) is running on port 8080 or 1080."""
    import socket
    for port, proto in [(8080, "http"), (1080, "socks5")]:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                proxy_url = f"{proto}://127.0.0.1:{port}"
                log(f"Verified active WARP proxy tunnel on port {port} ({proxy_url})!")
                return proxy_url
        except Exception:
            pass
    return None

def run_ytdlp_with_progress(cmd: list, env: dict, timeout: int = 40, stage_label: str = "Downloading stream") -> tuple[int, str]:
    """Execute yt-dlp while streaming stdout in real time with non-blocking queue to capture live byte progress and speeds without hangs."""
    log(f"Executing: {' '.join(cmd[:6])}...")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
        env=env
    )
    output_lines = []
    start_time = time.time()
    last_update = 0

    out_q = queue.Queue()
    def enqueue_output(out, q):
        try:
            for l in iter(out.readline, ''):
                q.put(l)
        except Exception:
            pass
        finally:
            try: out.close()
            except Exception: pass

    t = threading.Thread(target=enqueue_output, args=(proc.stdout, out_q), daemon=True)
    t.start()

    try:
        while True:
            try:
                line = out_q.get(timeout=0.3)
                output_lines.append(line)
                m = re.search(r'\[download\]\s+([\d\.]+)%\s+of\s+~?([\d\.]+\w+)(?:\s+at\s+([\d\.]+\w+/s))?(?:\s+ETA\s+(\S+))?', line)
                if m:
                    now = time.time()
                    if now - last_update >= 0.8:
                        last_update = now
                        sub_pct = float(m.group(1))
                        total_mb = m.group(2)
                        speed = m.group(3) or "10Gbps"
                        eta_str = m.group(4) or "1s"
                        scaled_pct = 52 + int(sub_pct * 0.36)
                        eta_sec = 2
                        if eta_str:
                            parts = eta_str.split(":")
                            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                                eta_sec = int(parts[0]) * 60 + int(parts[1])
                        report_progress(scaled_pct, f"⚡ {stage_label}: {sub_pct:.0f}% of {total_mb} ({speed})...", max(1, eta_sec))
            except queue.Empty:
                pass

            if proc.poll() is not None:
                # Drain remaining output lines
                while not out_q.empty():
                    output_lines.append(out_q.get_nowait())
                break

            if time.time() - start_time > timeout:
                proc.kill()
                log(f"Process timed out after {timeout}s!")
                break

        return proc.returncode if proc.returncode is not None else -1, "".join(output_lines)
    except Exception as e:
        try:
            proc.kill()
        except Exception:
            pass
        return -1, "".join(output_lines)

def download_stream_url(direct_url: str, target: Path, headers: Optional[dict] = None, proxy: Optional[str] = None) -> bool:
    """Stream download remote media URL into target path using 64KB buffers with live byte progress (supports curl_cffi + proxy)."""
    req_headers = {"User-Agent": GENERIC_CHROME_UA}
    if headers:
        req_headers.update(headers)

    # Prefer curl_cffi when proxy is requested or TLS impersonation helps
    if cf_requests and proxy:
        try:
            start_time = time.time()
            last_report = 0
            proxies = {"http": proxy, "https": proxy}
            with cf_requests.get(direct_url, impersonate="chrome", headers=req_headers, proxies=proxies, stream=True, timeout=45) as resp:
                if resp.status_code in (200, 206):
                    total_size = int(resp.headers.get("content-length") or 0)
                    downloaded = 0
                    with open(target, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=64 * 1024):
                            if not chunk:
                                continue
                            f.write(chunk)
                            downloaded += len(chunk)
                            now = time.time()
                            if now - last_report >= 0.8 and total_size > 0:
                                last_report = now
                                pct = 52 + int((downloaded / total_size) * 36)
                                mb_done = downloaded / (1024 * 1024)
                                mb_total = total_size / (1024 * 1024)
                                elapsed = max(0.01, now - start_time)
                                speed_mb = mb_done / elapsed
                                rem_sec = max(1, int((total_size - downloaded) / max(1, downloaded / elapsed)))
                                report_progress(pct, f"⚡ Streaming: {mb_done:.1f}/{mb_total:.1f} MB ({speed_mb:.1f} MB/s)...", rem_sec)
            if target.exists() and target.stat().st_size > 1000:
                log(f"Stream download (curl_cffi+proxy) SUCCESS: {target.name} ({target.stat().st_size} bytes)")
                return True
        except Exception as pe:
            log(f"curl_cffi proxy stream note on {direct_url[:60]}: {pe}")

    try:
        req = urllib.request.Request(direct_url, headers=req_headers)
        start_time = time.time()
        last_report = 0
        with urllib.request.urlopen(req, timeout=40) as s_resp, open(target, "wb") as f:
            total_size = int(s_resp.headers.get("Content-Length", 0))
            downloaded = 0
            while chunk := s_resp.read(64 * 1024):
                f.write(chunk)
                downloaded += len(chunk)
                now = time.time()
                if now - last_report >= 0.8:
                    last_report = now
                    if total_size > 0:
                        pct = 52 + int((downloaded / total_size) * 36)
                        mb_done = downloaded / (1024 * 1024)
                        mb_total = total_size / (1024 * 1024)
                        elapsed = max(0.01, now - start_time)
                        speed_mb = mb_done / elapsed
                        rem_sec = max(1, int((total_size - downloaded) / max(1, downloaded / elapsed)))
                        report_progress(pct, f"⚡ Streaming: {mb_done:.1f}/{mb_total:.1f} MB ({speed_mb:.1f} MB/s)...", rem_sec)
        if target.exists() and target.stat().st_size > 1000:
            log(f"Stream download SUCCESS: {target.name} ({target.stat().st_size} bytes)")
            return True
    except Exception as e:
        log(f"Stream download error on {direct_url[:60]}: {e}")

    # Last attempt via curl_cffi direct
    if cf_requests and not proxy:
        try:
            r = cf_requests.get(direct_url, impersonate="chrome", headers=req_headers, timeout=40)
            if r.status_code == 200 and len(r.content) > 1000:
                target.write_bytes(r.content)
                log(f"Stream download (curl_cffi) SUCCESS: {target.name} ({target.stat().st_size} bytes)")
                return True
        except Exception as ce:
            log(f"curl_cffi direct stream note: {ce}")
    return False

def get_latest_file(output_dir: Path, min_size: int = 1000, prefer_video: bool = False) -> Optional[Path]:
    files = list(output_dir.glob("*"))
    valid = [
        f for f in files
        if f.is_file() and not f.name.endswith(".part") and not f.name.endswith(".ytdl")
        and not f.name.startswith("temp_") and f.stat().st_size > min_size
    ]
    if not valid:
        return None

    # Check if there is already a cleanly merged file (without .fdash- or .f123 intermediate format tags)
    clean_merged = [
        f for f in valid
        if not re.search(r'\.f(?:dash-[a-zA-Z0-9_-]+|[0-9]+)\.[a-zA-Z0-9]+$', f.name)
    ]
    if prefer_video:
        clean_videos = [f for f in clean_merged if f.suffix.lower() in [".mp4", ".mkv", ".webm"]]
        if clean_videos:
            clean_videos.sort(key=lambda x: (x.stat().st_size, x.stat().st_mtime), reverse=True)
            return clean_videos[0]

        # If yt-dlp downloaded unmerged DASH video + audio tracks, merge them with FFmpeg automatically!
        dash_vids = [f for f in valid if f.suffix.lower() in [".mp4", ".webm", ".mkv"] and ".f" in f.name]
        dash_auds = [f for f in valid if f.suffix.lower() in [".m4a", ".aac", ".mp3", ".ogg", ".opus"] and ".f" in f.name]
        if dash_vids and dash_auds:
            dash_vids.sort(key=lambda x: x.stat().st_size, reverse=True)
            dash_auds.sort(key=lambda x: x.stat().st_size, reverse=True)
            v_track, a_track = dash_vids[0], dash_auds[0]
            base_name = re.sub(r'\.f(?:dash-[a-zA-Z0-9_-]+|[0-9]+)$', '', v_track.stem)
            merged_out = output_dir / f"{base_name}.mp4"
            log(f"Auto-muxing DASH video ({v_track.name}) + audio ({a_track.name}) -> {merged_out.name}...")
            try:
                subprocess.run([
                    "ffmpeg", "-y", "-i", str(v_track), "-i", str(a_track),
                    "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart",
                    str(merged_out)
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if merged_out.exists() and merged_out.stat().st_size > min_size:
                    try:
                        v_track.unlink()
                        a_track.unlink()
                    except Exception:
                        pass
                    return merged_out
            except Exception as me:
                log(f"Auto-mux note: {me}")
            return v_track

        video_files = [f for f in valid if f.suffix.lower() in [".mp4", ".mkv", ".webm"]]
        if video_files:
            video_files.sort(key=lambda x: (x.stat().st_size, x.stat().st_mtime), reverse=True)
            return video_files[0]

    if clean_merged:
        clean_merged.sort(key=lambda x: (x.stat().st_size, x.stat().st_mtime), reverse=True)
        return clean_merged[0]

    valid.sort(key=lambda x: (x.stat().st_size, x.stat().st_mtime), reverse=True)
    return valid[0]

# =====================================================================
# 1. TikTok Engine (TikWM Direct HD + Cobalt Rehydration Engine)
# =====================================================================
def download_tiktok_tikwm(url: str, output_dir: Path, is_audio: bool = False, proxy: Optional[str] = None) -> Optional[Path]:
    log("Attempting TikTok download via TikWM API (HD No Watermark)...")
    url = resolve_redirect_url(url)
    api_url = "https://www.tikwm.com/api/"
    post_data = urllib.parse.urlencode({"url": url, "hd": "1"}).encode("utf-8")
    req = urllib.request.Request(api_url, data=post_data, headers={"User-Agent": GENERIC_CHROME_UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("code") == 0 and "data" in data:
            d = data["data"]
            direct_url = d.get("music") if is_audio else (d.get("hdplay") or d.get("play") or d.get("wmplay"))
            if direct_url and direct_url.startswith("/"):
                direct_url = "https://www.tikwm.com" + direct_url
            vid_id = d.get("id") or extract_media_id(url)
            if not direct_url and d.get("images") and not is_audio:
                # TikTok Photo Slideshow: grab first high-res photo
                img_u = d["images"][0]
                target_img = output_dir / f"{vid_id}_OneForAllHub.jpg"
                if download_stream_url(img_u, target_img):
                    return target_img
            if direct_url:
                ext = "mp3" if is_audio else "mp4"
                target = output_dir / f"{vid_id}_OneForAllHub.{ext}"
                log(f"Downloading TikWM stream: {direct_url[:60]}...")
                if download_stream_url(direct_url, target):
                    return target
    except Exception as e:
        log(f"TikWM note: {e}")

    # Tier 2: Cobalt TikTok Rehydration Engine (__UNIVERSAL_DATA_FOR_REHYDRATION__)
    post_m = re.search(r'/(?:video|photo)/([0-9]+)', url)
    if post_m and cf_requests:
        post_id = post_m.group(1)
        log(f"TikTok Tier 2: Cobalt Rehydration extractor for {post_id}...")
        for use_p in ([proxy, None] if proxy else [None]):
            try:
                sess = cf_requests.Session(impersonate="chrome")
                proxies = {"http": use_p, "https": use_p} if use_p else None
                r = sess.get(f"https://www.tiktok.com/@i/video/{post_id}", headers={"User-Agent": GENERIC_CHROME_UA}, proxies=proxies, timeout=15)
                m = re.search(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">(.*?)</script>', r.text, re.DOTALL)
                if not m:
                    continue
                udata = json.loads(m.group(1))
                vdet = (udata.get("__DEFAULT_SCOPE__") or {}).get("webapp.video-detail") or {}
                if vdet.get("statusMsg"):
                    set_error_reason("unavailable", "This TikTok video is unavailable or deleted.")
                    continue
                detail = (vdet.get("itemInfo") or {}).get("itemStruct") or {}
                cookie_hdr = "; ".join(f"{k}={v}" for k, v in sess.cookies.items())
                dl_headers = {"User-Agent": GENERIC_CHROME_UA, "Referer": "https://www.tiktok.com/", "Cookie": cookie_hdr}
                if is_audio:
                    aud_url = (detail.get("music") or {}).get("playUrl") or (detail.get("video") or {}).get("playAddr")
                    if aud_url:
                        target = output_dir / f"{post_id}_OneForAllHub.mp3"
                        if download_stream_url(aud_url, target, headers=dl_headers, proxy=use_p):
                            return target
                else:
                    play_url = (detail.get("video") or {}).get("playAddr")
                    if play_url:
                        target = output_dir / f"{post_id}_OneForAllHub.mp4"
                        if download_stream_url(play_url, target, headers=dl_headers, proxy=use_p):
                            return target
                    imgs = (detail.get("imagePost") or {}).get("images") or []
                    if imgs:
                        url_list = (imgs[0].get("imageURL") or {}).get("urlList") or []
                        if url_list:
                            target = output_dir / f"{post_id}_OneForAllHub.jpg"
                            if download_stream_url(url_list[0], target, headers=dl_headers, proxy=use_p):
                                return target
            except Exception as ce:
                log(f"TikTok Cobalt Rehydration note (proxy={bool(use_p)}): {ce}")
    return None

# =====================================================================
# 2. Twitter / X Dedicated Engine (FxTwitter + Cobalt Syndication + Twitsave)
# =====================================================================
def _twitter_syndication_token(tweet_id: str) -> str:
    """Cobalt/yt-dlp Syndication Embed API token formula."""
    val = (int(tweet_id) / 1e15) * math.pi
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    int_part = int(val)
    frac_part = val - int_part
    res = ""
    if int_part == 0:
        res = "0"
    else:
        n = int_part
        while n > 0:
            res = chars[n % 36] + res
            n //= 36
    frac_str = ""
    for _ in range(12):
        frac_part *= 36
        d = int(frac_part)
        frac_str += chars[d]
        frac_part -= d
    return re.sub(r'(0+|\.)', '', res + frac_str)

def download_twitter(url: str, output_dir: Path, fmt: str, proxy: Optional[str] = None) -> Optional[Path]:
    log("Attempting Twitter / X download via FxTwitter / Cobalt Syndication / Twitsave engine...")
    report_progress(50, "Extracting Twitter / X high-bitrate stream...")
    clean_id = extract_media_id(url)
    is_audio = fmt == "audio-mp3"
    target_ext = "mp3" if is_audio else "mp4"
    final_file = output_dir / f"{clean_id}_OneForAllHub.{target_ext}"

    # Tier 1: FxTwitter JSON API (< 200ms)
    try:
        fx_url = re.sub(r'https?://(?:www\.)?(?:twitter\.com|x\.com)/', 'https://api.fxtwitter.com/', url)
        req_fx = urllib.request.Request(fx_url, headers={"User-Agent": "OneForAllDownloader/2.0"})
        with urllib.request.urlopen(req_fx, timeout=10) as r_fx:
            fx_data = json.loads(r_fx.read().decode("utf-8"))
        tweet = fx_data.get("tweet") or {}
        media_obj = tweet.get("media") or {}
        videos = media_obj.get("videos") or media_obj.get("all") or []
        if videos:
            v0 = videos[0]
            if v0.get("type") == "photo" and v0.get("url") and not is_audio:
                photo_url = v0["url"].split("?")[0] + "?name=4096x4096"
                img_dest = output_dir / f"{clean_id}_OneForAllHub.jpg"
                if download_stream_url(photo_url, img_dest):
                    return img_dest
            variants = [v for v in (v0.get("variants") or []) if v.get("content_type") == "video/mp4" and v.get("url")]
            variants.sort(key=lambda x: x.get("bitrate", 0), reverse=True)
            chosen_url = v0.get("url")
            if variants:
                if fmt == "video-720p":
                    for v in variants:
                        if "720" in v["url"]:
                            chosen_url = v["url"]
                            break
                else:
                    chosen_url = variants[0]["url"]
            if chosen_url:
                log(f"FxTwitter resolved direct stream: {chosen_url[:80]}...")
                temp_mp4 = output_dir / f"temp_{clean_id}.mp4" if is_audio else final_file
                if download_stream_url(chosen_url, temp_mp4):
                    if is_audio:
                        subprocess.run([
                            "ffmpeg", "-y", "-threads", "0", "-i", str(temp_mp4),
                            "-vn", "-ar", "44100", "-ac", "2", "-b:a", "192k",
                            str(final_file)
                        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        try: temp_mp4.unlink()
                        except Exception: pass
                    if final_file.exists() and final_file.stat().st_size > 1000:
                        return final_file
    except Exception as fx_e:
        log(f"FxTwitter note: {fx_e}")

    # Tier 1.5: Cobalt Twitter Syndication API (Official Twitter CDN, zero-auth)
    tw_id_m = re.search(r'status/([0-9]+)', url)
    if tw_id_m:
        try:
            tid = tw_id_m.group(1)
            tok = _twitter_syndication_token(tid)
            syn_url = f"https://cdn.syndication.twimg.com/tweet-result?id={tid}&token={tok}"
            req_syn = urllib.request.Request(syn_url, headers={"User-Agent": GENERIC_CHROME_UA})
            with urllib.request.urlopen(req_syn, timeout=10) as r_syn:
                syn_data = json.loads(r_syn.read().decode("utf-8"))
            mdetails = syn_data.get("mediaDetails") or []
            if mdetails:
                m0 = mdetails[0]
                if m0.get("type") == "photo" and m0.get("media_url_https") and not is_audio:
                    photo_url = f"{m0['media_url_https']}?name=4096x4096"
                    img_dest = output_dir / f"{clean_id}_OneForAllHub.jpg"
                    if download_stream_url(photo_url, img_dest):
                        log(f"Twitter Cobalt Syndication SUCCESS (Photo): {img_dest.name}")
                        return img_dest
                v_info = m0.get("video_info") or {}
                variants = [v for v in (v_info.get("variants") or []) if v.get("content_type") == "video/mp4" and v.get("url")]
                if variants:
                    variants.sort(key=lambda x: int(x.get("bitrate") or 0), reverse=True)
                    chosen_url = variants[0]["url"]
                    log(f"Twitter Cobalt Syndication resolved stream: {chosen_url[:80]}...")
                    temp_mp4 = output_dir / f"temp_{clean_id}.mp4" if is_audio else final_file
                    if download_stream_url(chosen_url, temp_mp4):
                        if is_audio:
                            subprocess.run([
                                "ffmpeg", "-y", "-threads", "0", "-i", str(temp_mp4),
                                "-vn", "-ar", "44100", "-ac", "2", "-b:a", "192k",
                                str(final_file)
                            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            try: temp_mp4.unlink()
                            except Exception: pass
                        if final_file.exists() and final_file.stat().st_size > 1000:
                            return final_file
        except Exception as syn_e:
            log(f"Twitter Cobalt Syndication note: {syn_e}")

    try:
        encoded = urllib.parse.quote(url)
        api_url = f"https://twitsave.com/info?url={encoded}"
        req = urllib.request.Request(api_url, headers={"User-Agent": GENERIC_CHROME_UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode('utf-8', errors='ignore')

        matches = re.findall(r'href=["\'](https?://[^"\']*(?:video\.twimg\.com|twitsave\.com/download)[^"\']*)["\']', html)
        direct_candidates = []
        for m in matches:
            if "twitsave.com/download?file=" in m:
                b64_part = m.split("file=")[1]
                try:
                    raw_url = base64.b64decode(urllib.parse.unquote(b64_part)).decode('utf-8')
                    direct_candidates.append(raw_url)
                except Exception:
                    pass
            elif "video.twimg.com" in m:
                direct_candidates.append(m)

        if direct_candidates:
            def get_cand_res(u):
                m = re.search(r'(\d+)x(\d+)', u)
                if m:
                    return int(m.group(1)) * int(m.group(2))
                return 0
            direct_candidates.sort(key=get_cand_res, reverse=True)

            chosen_url = None
            if fmt == "video-720p":
                for c in direct_candidates:
                    if "1280x720" in c or "720" in c:
                        chosen_url = c
                        break
            elif fmt == "video-1080p":
                for c in direct_candidates:
                    if "1920x1080" in c or "1080" in c:
                        chosen_url = c
                        break

            if not chosen_url:
                chosen_url = direct_candidates[0]

            log(f"Selected direct Twitter stream: {chosen_url[:80]}...")
            temp_mp4 = output_dir / f"temp_{clean_id}.mp4" if is_audio else final_file

            if download_stream_url(chosen_url, temp_mp4):
                if is_audio:
                    log("Converting Twitter video audio to 192k MP3 via FFmpeg...")
                    try:
                        subprocess.run([
                            "ffmpeg", "-y", "-threads", "0", "-i", str(temp_mp4),
                            "-vn", "-ar", "44100", "-ac", "2", "-b:a", "192k",
                            str(final_file)
                        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    except Exception as fe:
                        log(f"FFmpeg conversion note: {fe}")
                    try:
                        temp_mp4.unlink()
                    except Exception:
                        pass
                    if final_file.exists() and final_file.stat().st_size > 1000:
                        log(f"Twitter SUCCESS (Audio MP3): {final_file.name} ({final_file.stat().st_size} bytes)")
                        return final_file
                else:
                    log(f"Twitter SUCCESS (Video MP4): {final_file.name} ({final_file.stat().st_size} bytes)")
                    return final_file
    except Exception as e:
        log(f"Twitsave engine note: {e}")

    # Fallback to general yt-dlp
    log("Twitter fallback to general yt-dlp...")
    return download_general_ytdlp(url, output_dir, fmt, proxy=proxy)

# =====================================================================
# 3. Instagram Engine (Full Cobalt Architecture: Embed + Web API PR#1619 + Mobile Liger + Polaris GQL + Stories + yt-dlp)
# =====================================================================
IG_COMMON_HEADERS = {
    "user-agent": GENERIC_CHROME_UA,
    "sec-gpc": "1",
    "sec-fetch-site": "same-origin",
    "x-ig-app-id": "936619743392459",
}

IG_MOBILE_HEADERS = {
    "x-ig-app-locale": "en_US",
    "x-ig-device-locale": "en_US",
    "x-ig-mapped-locale": "en_US",
    "user-agent": "Instagram 275.0.0.27.98 Android (33/13; 280dpi; 720x1423; Xiaomi; Redmi 7; onclite; qcom; en_US; 458229237)",
    "accept-language": "en-US",
    "x-fb-http-engine": "Liger",
    "x-fb-client-ip": "True",
    "x-fb-server-cluster": "True",
}

IG_EMBED_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Cache-Control": "max-age=0",
    "Dnt": "1",
    "Priority": "u=0, i",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": GENERIC_CHROME_UA,
}

def _ig_shortcode_to_pk(shortcode: str) -> Optional[str]:
    """Decode Instagram shortcode to numeric media PK (base64 alphabet)."""
    alpha = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    try:
        # Strip any private suffix beyond standard 11-char shortcode if present
        sc = shortcode.strip()
        if not sc:
            return None
        n = 0
        for ch in sc:
            idx = alpha.find(ch)
            if idx < 0:
                return None
            n = n * 64 + idx
        return str(n)
    except Exception:
        return None

def _ig_get_obj_from_entries(name: str, html: str) -> Optional[dict]:
    m = re.search(r'\["' + re.escape(name) + r'",.*?,(\{.*?\}),\d+\]', html)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    return None

def _ig_get_num_from_query(name: str, html: str) -> Optional[str]:
    m = re.search(re.escape(name) + r'=(\d+)', html)
    return m.group(1) if m else None

def _ig_http_get(url: str, headers: dict, proxy: Optional[str] = None, timeout: int = 14) -> tuple[int, str]:
    if cf_requests:
        proxies = {"http": proxy, "https": proxy} if proxy else None
        r = cf_requests.get(url, impersonate="chrome", headers=headers, proxies=proxies, timeout=timeout)
        return r.status_code, r.text
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", errors="ignore")

def _ig_http_post(url: str, headers: dict, data: dict, proxy: Optional[str] = None, timeout: int = 14) -> tuple[int, str]:
    if cf_requests:
        proxies = {"http": proxy, "https": proxy} if proxy else None
        r = cf_requests.post(url, impersonate="chrome", headers=headers, data=data, proxies=proxies, timeout=timeout)
        return r.status_code, r.text
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", errors="ignore")

def _ig_extract_old_post(gql_data: dict) -> Optional[tuple[str, bool, str]]:
    """Cobalt extractOldPost(): handles single video, single photo, and sidecar carousels."""
    if not isinstance(gql_data, dict):
        return None
    sm = gql_data.get("shortcode_media") or gql_data.get("xdt_shortcode_media")
    if not isinstance(sm, dict):
        return None

    sidecar = sm.get("edge_sidecar_to_children")
    if isinstance(sidecar, dict) and sidecar.get("edges"):
        edges = sidecar["edges"]
        # Prefer first video in carousel, else first high-res photo
        for edge in edges:
            node = edge.get("node") or {}
            if node.get("is_video") and node.get("video_url"):
                return node["video_url"], False, "mp4"
        for edge in edges:
            node = edge.get("node") or {}
            if node.get("display_url"):
                return node["display_url"], True, "jpg"

    if sm.get("video_url"):
        return sm["video_url"], False, "mp4"
    if sm.get("display_url"):
        return sm["display_url"], True, "jpg"
    return None

def _ig_extract_new_post(item: dict) -> Optional[tuple[str, bool, str]]:
    """Cobalt extractNewPost(): handles Mobile/Web API items (Reels, Posts, Carousels, Stories)."""
    if not isinstance(item, dict):
        return None
    if (item.get("user") or {}).get("is_private"):
        set_error_reason("private", "This Instagram account or post is private.")
        return None

    carousel = item.get("carousel_media")
    if isinstance(carousel, list) and carousel:
        for entry in carousel:
            vids = entry.get("video_versions") or []
            if vids:
                best = max(vids, key=lambda v: int(v.get("width") or 0) * int(v.get("height") or 0))
                if best.get("url"):
                    return best["url"], False, "mp4"
        for entry in carousel:
            cands = (entry.get("image_versions2") or {}).get("candidates") or []
            if cands:
                best_i = max(cands, key=lambda c: int(c.get("width") or 0) * int(c.get("height") or 0))
                if best_i.get("url"):
                    return best_i["url"], True, "jpg"

    vids = item.get("video_versions") or []
    if vids:
        best = max(vids, key=lambda v: int(v.get("width") or 0) * int(v.get("height") or 0))
        if best.get("url"):
            return best["url"], False, "mp4"

    # Guard from Cobalt PR#1619: if media_type==2 (video) has no video_versions, don't mistakenly return cover thumbnail!
    if item.get("media_type") == 2 and not vids:
        return None

    cands = (item.get("image_versions2") or {}).get("candidates") or []
    if cands:
        best_i = max(cands, key=lambda c: int(c.get("width") or 0) * int(c.get("height") or 0))
        if best_i.get("url"):
            return best_i["url"], True, "jpg"
    return None

def _ig_finalize_media(media_url: str, is_photo: bool, ext: str, output_dir: Path, clean_id: str, is_audio: bool, proxy: Optional[str] = None) -> Optional[Path]:
    """Download resolved Instagram CDN media (direct or via WARP) and convert to MP3 if audio requested."""
    if is_photo and is_audio:
        log("Instagram post is an image-only asset; delivering high-resolution image.")
    if is_photo:
        dest = output_dir / f"{clean_id}_OneForAllHub.{ext}"
        if download_stream_url(media_url, dest) or (proxy and download_stream_url(media_url, dest, proxy=proxy)):
            return dest
        return None

    final_file = output_dir / f"{clean_id}_OneForAllHub.{'mp3' if is_audio else 'mp4'}"
    temp_mp4 = output_dir / f"temp_{clean_id}.mp4" if is_audio else final_file
    if download_stream_url(media_url, temp_mp4) or (proxy and download_stream_url(media_url, temp_mp4, proxy=proxy)):
        if is_audio:
            log("Converting Instagram video audio to 192k MP3 via FFmpeg...")
            try:
                subprocess.run([
                    "ffmpeg", "-y", "-threads", "0", "-i", str(temp_mp4),
                    "-vn", "-ar", "44100", "-ac", "2", "-b:a", "192k",
                    str(final_file)
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as fe:
                log(f"FFmpeg IG audio conversion note: {fe}")
            try:
                temp_mp4.unlink()
            except Exception:
                pass
            if final_file.exists() and final_file.stat().st_size > 1000:
                return final_file
        else:
            if final_file.exists() and final_file.stat().st_size > 1000:
                return final_file
    return None

def download_instagram(url: str, output_dir: Path, fmt: str, proxy: Optional[str] = None) -> Optional[Path]:
    log("Attempting Instagram download via Cobalt Multi-Tier Engine...")
    report_progress(50, "Bypassing Instagram restrictions via Cobalt Engine...")
    url = sanitize_url(url)
    clean_id = extract_media_id(url)
    is_audio = fmt == "audio-mp3"

    ig_cookie_str, ig_cookie_dict = load_domain_cookies(["instagram.com"])
    ig_csrf = ig_cookie_dict.get("csrftoken", "")
    proxy_order = [proxy, None] if proxy else [None]

    # ------------------------------------------------------------------
    # Tier 0: Instagram Stories (/stories/<username>/<storyId>/) - Cobalt getStory()
    # ------------------------------------------------------------------
    story_m = re.search(r'/stories/([^/]+)/([0-9]+)', url)
    if story_m:
        username, story_id = story_m.group(1), story_m.group(2)
        log(f"Instagram Story detected: user={username}, story_id={story_id}")
        if ig_cookie_str:
            for use_p in proxy_order:
                try:
                    auth_headers = {
                        **IG_COMMON_HEADERS,
                        "x-csrftoken": ig_csrf,
                        "x-ig-www-claim": "0",
                        "cookie": ig_cookie_str,
                    }
                    _, prof_txt = _ig_http_get(
                        f"https://www.instagram.com/api/v1/users/web_profile_info/?username={urllib.parse.quote(username)}",
                        auth_headers, proxy=use_p
                    )
                    user_id = ((json.loads(prof_txt).get("data") or {}).get("user") or {}).get("id")
                    if not user_id:
                        continue
                    _, home_html = _ig_http_get("https://www.instagram.com/", auth_headers, proxy=use_p)
                    dtsg_m = re.search(r'"dtsg":\{"token":"(.*?)"', home_html)
                    if not dtsg_m:
                        continue
                    post_hdrs = {**auth_headers, "content-type": "application/x-www-form-urlencoded"}
                    _, st_txt = _ig_http_post(
                        "https://www.instagram.com/api/graphql/",
                        post_hdrs,
                        {
                            "fb_dtsg": dtsg_m.group(1),
                            "jazoest": "26438",
                            "variables": json.dumps({"reel_ids_arr": [str(user_id)]}),
                            "server_timestamps": "true",
                            "doc_id": "25317500907894419",
                        },
                        proxy=use_p
                    )
                    reels_media = (((json.loads(st_txt).get("data") or {}).get("xdt_api__v1__feed__reels_media") or {}).get("reels_media") or [])
                    for rm in reels_media:
                        if str(rm.get("id")) == str(user_id):
                            for it in (rm.get("items") or []):
                                if str(it.get("pk")) == str(story_id):
                                    ext_res = _ig_extract_new_post(it)
                                    if ext_res:
                                        f = _ig_finalize_media(*ext_res, output_dir, clean_id, is_audio, proxy=proxy)
                                        if f:
                                            log(f"Instagram Cobalt Story SUCCESS: {f.name}")
                                            return f
                except Exception as se:
                    log(f"Instagram Cobalt Story note (proxy={bool(use_p)}): {se}")

    # Extract shortcode for Reels / Posts / TV (/reel/, /reels/, /p/, /tv/, /<user>/reel/, /<user>/p/)
    sc_m = re.search(r'/(?:reels?|p|tv)/([a-zA-Z0-9_-]+)', url)
    shortcode = sc_m.group(1) if sc_m else None

    if shortcode:
        # ------------------------------------------------------------------
        # Tier 1: Cobalt Captioned Embed (/p/<sc>/embed/captioned/) - Instant, Zero-Cookie
        # ------------------------------------------------------------------
        log(f"Instagram Tier 1 (Cobalt Embed Captioned) for {shortcode}...")
        report_progress(54, "Extracting Instagram stream via Cobalt Embed...")
        embed_attempts = [(None, False)]
        if proxy:
            embed_attempts.append((proxy, False))
        if ig_cookie_str:
            embed_attempts.append((proxy if proxy else None, True))
        for use_p, use_ck in embed_attempts:
            try:
                hdrs = {**IG_EMBED_HEADERS}
                if use_ck and ig_cookie_str:
                    hdrs["cookie"] = ig_cookie_str
                status, html = _ig_http_get(f"https://www.instagram.com/p/{shortcode}/embed/captioned/", hdrs, proxy=use_p)
                if status == 200 and html:
                    m = re.search(r'"init",\[\],\[(.*?)\]\],', html)
                    if m:
                        ed = json.loads(m.group(1))
                        if isinstance(ed, dict) and ed.get("contextJSON"):
                            ctx = json.loads(ed["contextJSON"])
                            ext_res = _ig_extract_old_post(ctx.get("gql_data"))
                            if ext_res:
                                log(f"Cobalt Embed resolved media (is_photo={ext_res[1]}, proxy={bool(use_p)})!")
                                f = _ig_finalize_media(*ext_res, output_dir, clean_id, is_audio, proxy=proxy)
                                if f:
                                    log(f"Instagram Tier 1 (Cobalt Embed) SUCCESS: {f.name} ({f.stat().st_size} bytes)")
                                    return f
            except Exception as ee:
                log(f"Instagram Tier 1 (Cobalt Embed) note: {ee}")

        # Resolve numeric media PK (mathematically first, fallback to oEmbed API)
        media_pk = _ig_shortcode_to_pk(shortcode)
        if not media_pk:
            try:
                oembed_url = f"https://i.instagram.com/api/v1/oembed/?url={urllib.parse.quote(f'https://www.instagram.com/p/{shortcode}/')}"
                _, oe_txt = _ig_http_get(oembed_url, IG_MOBILE_HEADERS, proxy=proxy)
                media_pk = json.loads(oe_txt).get("media_id")
            except Exception:
                pass

        # ------------------------------------------------------------------
        # Tier 2: Cobalt PR #1619 Web Media Info API (Solves Age-Gated / Embed-Broken Reels!)
        # ------------------------------------------------------------------
        if media_pk and ig_cookie_str:
            log(f"Instagram Tier 2 (Cobalt PR#1619 Web API) for {shortcode} (pk={media_pk})...")
            report_progress(58, "Extracting age-gated / protected Instagram media via Web API...")
            for use_p in proxy_order:
                try:
                    web_hdrs = {
                        **IG_COMMON_HEADERS,
                        "x-csrftoken": ig_csrf,
                        "x-ig-www-claim": "0",
                        "cookie": ig_cookie_str,
                    }
                    status, txt = _ig_http_get(f"https://www.instagram.com/api/v1/media/{media_pk}/info/", web_hdrs, proxy=use_p)
                    if status == 200:
                        data = json.loads(txt)
                        items = data.get("items") or []
                        if items:
                            ext_res = _ig_extract_new_post(items[0])
                            if ext_res:
                                log(f"Cobalt PR#1619 Web API resolved media (is_photo={ext_res[1]}, proxy={bool(use_p)})!")
                                f = _ig_finalize_media(*ext_res, output_dir, clean_id, is_audio, proxy=proxy)
                                if f:
                                    log(f"Instagram Tier 2 (Cobalt Web API) SUCCESS: {f.name} ({f.stat().st_size} bytes)")
                                    return f
                    else:
                        log(f"Cobalt Web API status={status} (proxy={bool(use_p)}): {txt[:140]}")
                except Exception as we:
                    log(f"Instagram Tier 2 (Cobalt Web API) note: {we}")

        # ------------------------------------------------------------------
        # Tier 3: Cobalt Mobile Liger API (i.instagram.com/api/v1/media/<pk>/info/)
        # ------------------------------------------------------------------
        if media_pk:
            log(f"Instagram Tier 3 (Cobalt Mobile Liger API) for pk={media_pk}...")
            mob_attempts = [(proxy, False), (None, False)] if proxy else [(None, False)]
            if ig_cookie_str:
                mob_attempts.append((proxy if proxy else None, True))
            for use_p, use_ck in mob_attempts:
                try:
                    m_hdrs = {**IG_MOBILE_HEADERS}
                    if use_ck and ig_cookie_str:
                        m_hdrs["cookie"] = ig_cookie_str
                    status, txt = _ig_http_get(f"https://i.instagram.com/api/v1/media/{media_pk}/info/", m_hdrs, proxy=use_p)
                    if status == 200:
                        items = (json.loads(txt).get("items") or [])
                        if items:
                            ext_res = _ig_extract_new_post(items[0])
                            if ext_res:
                                f = _ig_finalize_media(*ext_res, output_dir, clean_id, is_audio, proxy=proxy)
                                if f:
                                    log(f"Instagram Tier 3 (Cobalt Mobile API) SUCCESS: {f.name} ({f.stat().st_size} bytes)")
                                    return f
                except Exception as me:
                    log(f"Instagram Tier 3 (Cobalt Mobile API) note: {me}")

        # ------------------------------------------------------------------
        # Tier 4: Cobalt Polaris Web GraphQL API (doc_id: 8845758582119845 + 10015901848480474 + Inline HTML)
        # ------------------------------------------------------------------
        log(f"Instagram Tier 4 (Cobalt Polaris GraphQL) for {shortcode}...")
        report_progress(62, "Querying Instagram Polaris GraphQL API...")
        gql_attempts = [(proxy, True), (None, True), (proxy, False)] if (proxy and ig_cookie_str) else ([(None, True), (None, False)] if ig_cookie_str else [(proxy, False), (None, False)])
        for use_p, use_ck in gql_attempts:
            try:
                pg_hdrs = {**IG_EMBED_HEADERS}
                if use_ck and ig_cookie_str:
                    pg_hdrs["cookie"] = ig_cookie_str
                _, phtml = _ig_http_get(f"https://www.instagram.com/p/{shortcode}/", pg_hdrs, proxy=use_p)
                if not phtml:
                    continue

                # Check inline video_versions / video_url embedded in SSR HTML first
                inline_v = re.search(r'"video_url":"(https:[^"]+)"', phtml)
                if inline_v:
                    v_u = inline_v.group(1).replace("\\/", "/").encode("utf-8").decode("unicode_escape")
                    f = _ig_finalize_media(v_u, False, "mp4", output_dir, clean_id, is_audio, proxy=proxy)
                    if f:
                        log(f"Instagram Tier 4a (Inline SSR HTML) SUCCESS: {f.name}")
                        return f

                site_data = _ig_get_obj_from_entries("SiteData", phtml) or {}
                polaris = _ig_get_obj_from_entries("PolarisSiteData", phtml) or {}
                web_cfg = _ig_get_obj_from_entries("DGWWebConfig", phtml) or {}
                push_info = _ig_get_obj_from_entries("InstagramWebPushInfo", phtml) or {}
                lsd = (_ig_get_obj_from_entries("LSD", phtml) or {}).get("token") or secrets.token_urlsafe(8)
                csrf = (_ig_get_obj_from_entries("InstagramSecurityConfig", phtml) or {}).get("csrf_token") or ig_csrf
                bloks = (_ig_get_obj_from_entries("WebBloksVersioningID", phtml) or {}).get("versioningID") or ""

                anon_cookie = "; ".join([x for x in [
                    csrf and f"csrftoken={csrf}",
                    polaris.get("device_id") and f"ig_did={polaris['device_id']}",
                    "wd=1280x720", "dpr=2",
                    polaris.get("machine_id") and f"mid={polaris['machine_id']}",
                    "ig_nrcb=1",
                ] if x])

                gql_hdrs = {
                    **IG_EMBED_HEADERS,
                    "x-ig-app-id": str(web_cfg.get("appId") or "936619743392459"),
                    "X-FB-LSD": lsd,
                    "X-CSRFToken": csrf,
                    "x-asbd-id": "129477",
                    "cookie": ig_cookie_str if (use_ck and ig_cookie_str) else anon_cookie,
                    "content-type": "application/x-www-form-urlencoded",
                    "X-FB-Friendly-Name": "PolarisPostActionLoadPostQueryQuery",
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-origin",
                }
                if bloks:
                    gql_hdrs["X-Bloks-Version-Id"] = bloks

                for doc_id in ["8845758582119845", "10015901848480474"]:
                    gql_body = {
                        "__d": "www",
                        "__a": "1",
                        "__s": "::" + "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=6)),
                        "__hs": site_data.get("haste_session") or "20126.HYP:instagram_web_pkg.2.1...0",
                        "__req": "b",
                        "__ccg": "EXCELLENT",
                        "__rev": str(push_info.get("rollout_hash") or "1019933358"),
                        "__hsi": str(site_data.get("hsi") or "7436540909012459023"),
                        "__dyn": secrets.token_urlsafe(154),
                        "__csr": secrets.token_urlsafe(154),
                        "__user": "0",
                        "__comet_req": _ig_get_num_from_query("__comet_req", phtml) or "7",
                        "av": "0",
                        "dpr": "2",
                        "lsd": lsd,
                        "jazoest": _ig_get_num_from_query("jazoest", phtml) or str(random.randint(1000, 9999)),
                        "__spin_r": str(site_data.get("__spin_r") or "1019933358"),
                        "__spin_b": str(site_data.get("__spin_b") or "trunk"),
                        "__spin_t": str(site_data.get("__spin_t") or int(time.time())),
                        "fb_api_caller_class": "RelayModern",
                        "fb_api_req_friendly_name": "PolarisPostActionLoadPostQueryQuery",
                        "variables": json.dumps({
                            "shortcode": shortcode,
                            "fetch_tagged_user_count": None,
                            "hoisted_comment_id": None,
                            "hoisted_reply_id": None,
                        }),
                        "server_timestamps": "true",
                        "doc_id": doc_id,
                    }
                    st_g, txt_g = _ig_http_post("https://www.instagram.com/graphql/query", gql_hdrs, gql_body, proxy=use_p)
                    if st_g == 200:
                        g_json = json.loads(txt_g)
                        ext_res = _ig_extract_old_post(g_json.get("data"))
                        if ext_res:
                            f = _ig_finalize_media(*ext_res, output_dir, clean_id, is_audio, proxy=proxy)
                            if f:
                                log(f"Instagram Tier 4 (Cobalt Polaris GQL doc={doc_id}) SUCCESS: {f.name}")
                                return f
            except Exception as ge:
                log(f"Instagram Tier 4 (Cobalt Polaris GQL) note: {ge}")

    # ------------------------------------------------------------------
    # Tier 5: yt-dlp Fallback (Authenticated Temp Cookies + Anonymous, via WARP)
    # ------------------------------------------------------------------
    log("Instagram Tier 5: yt-dlp fallback (authenticated + anonymous)...")
    env_with_proxy = {**os.environ}
    if proxy:
        env_with_proxy["HTTP_PROXY"] = proxy
        env_with_proxy["HTTPS_PROXY"] = proxy
        env_with_proxy["http_proxy"] = proxy
        env_with_proxy["https_proxy"] = proxy
        env_with_proxy["NO_PROXY"] = "127.0.0.1,localhost"
        env_with_proxy["no_proxy"] = "127.0.0.1,localhost"

    for use_ck in ([True, False] if ig_cookie_str else [False]):
        c_args = get_cookie_args(url, allow_instagram=True) if use_ck else []
        cmd = [
            *get_ytdlp_cmd(),
            "--no-playlist",
            "--retries", "2",
            "--socket-timeout", "18",
            "--paths", str(output_dir),
            "-o", f"{clean_id}_OneForAllHub.%(ext)s",
        ] + c_args
        if is_audio:
            cmd.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
        else:
            cmd.extend(["-f", "bv*+ba/b[height<=1080]/b", "--merge-output-format", "mp4"])
        if proxy:
            cmd.extend(["--proxy", proxy])
        cmd.append(url)
        try:
            _, out_s = run_ytdlp_with_progress(cmd, env_with_proxy, timeout=35, stage_label="Downloading Instagram media")
            log(f"Instagram Tier 5 (cookies={use_ck}) output:\n{out_s[-400:]}")
            f = get_latest_file(output_dir, prefer_video=not is_audio)
            if f and f.stat().st_size > 1000:
                log(f"Instagram Tier 5 SUCCESS: {f.name} ({f.stat().st_size} bytes)")
                return f
        except Exception as ye:
            log(f"Instagram Tier 5 note: {ye}")

    # Tier 6: Cobalt Error Context detection (Private / Age-Restricted diagnosis)
    if shortcode:
        try:
            _, phtml = _ig_http_get(f"https://www.instagram.com/p/{shortcode}/", IG_EMBED_HEADERS, proxy=proxy)
            if '"tracePolicy":"polaris.privatePostPage"' in phtml or "This account is private" in phtml:
                set_error_reason("private", "This Instagram account or post is private.")
            elif "Restricted" in phtml or "age-restricted" in phtml.lower():
                set_error_reason("age", "This Instagram post is age-restricted.")
        except Exception:
            pass
    return None

# =====================================================================
# =====================================================================
# 4. YouTube Engine (BGUtil PO-Token + pytubefix WEB + SaveTube CDN)
# =====================================================================
def download_youtube_savetube(url: str, output_dir: Path, fmt: str, clean_id: str) -> Optional[Path]:
    """External SaveTube CDN API fallback (AES-128-CBC decrypted via system openssl)."""
    log("Invoking SaveTube CDN external YouTube fallback engine...")
    report_progress(68, "Downloading via high-speed YouTube CDN mirror...")
    st_headers = {
        "Content-Type": "application/json",
        "Origin": "https://ytsave.savetube.me",
        "Referer": "https://ytsave.savetube.me/",
        "User-Agent": GENERIC_CHROME_UA
    }
    try:
        cdn_req = urllib.request.Request("https://media.savetube.me/api/random-cdn", headers={"User-Agent": GENERIC_CHROME_UA})
        with urllib.request.urlopen(cdn_req, timeout=10) as r:
            cdn_host = json.loads(r.read().decode("utf-8"))["cdn"]

        info_req = urllib.request.Request(
            f"https://{cdn_host}/v2/info",
            data=json.dumps({"url": url}).encode("utf-8"),
            headers=st_headers,
            method="POST"
        )
        with urllib.request.urlopen(info_req, timeout=15) as r:
            info = json.loads(r.read().decode("utf-8"))
        if not info.get("status") or not info.get("data"):
            log(f"SaveTube v2/info returned status={info.get('status')}")
            return None

        enc_b64 = re.sub(r"\s+", "", info["data"])
        raw_bytes = base64.b64decode(enc_b64)
        iv_hex = raw_bytes[:16].hex()
        ciphertext = raw_bytes[16:]
        proc = subprocess.run(
            ["openssl", "enc", "-d", "-aes-128-cbc", "-K", "C5D58EF67A7584E4A29F6C35BBC4EB12", "-iv", iv_hex],
            input=ciphertext,
            capture_output=True,
            timeout=10,
            check=True
        )
        media_data = json.loads(proc.stdout.decode("utf-8"))

        is_audio = fmt == "audio-mp3"
        if is_audio:
            dl_type = "audio"
            ext = "mp3"
            aud_quals = [str(a.get("quality")) for a in (media_data.get("audio_formats") or []) if a.get("quality") is not None]
            qual = "192" if "192" in aud_quals else ("128" if "128" in aud_quals else (aud_quals[0] if aud_quals else "128"))
        else:
            dl_type = "video"
            ext = "mp4"
            target_map = {"video-1080p": 1080, "video-720p": 720, "video-480p": 480, "video-360p": 360, "video-best": 1080}
            target_h = target_map.get(fmt, 720)
            vid_quals = sorted(
                {int(str(v.get("quality"))) for v in (media_data.get("video_formats") or []) if str(v.get("quality", "")).isdigit()},
                reverse=True
            )
            eligible = [q for q in vid_quals if q <= target_h]
            qual = str(eligible[0]) if eligible else (str(vid_quals[-1]) if vid_quals else "720")

        dl_req = urllib.request.Request(
            f"https://{cdn_host}/download",
            data=json.dumps({
                "id": media_data["id"],
                "key": media_data["key"],
                "downloadType": dl_type,
                "quality": str(qual)
            }).encode("utf-8"),
            headers=st_headers,
            method="POST"
        )
        with urllib.request.urlopen(dl_req, timeout=20) as r:
            dl_json = json.loads(r.read().decode("utf-8"))
        dl_url = (dl_json.get("data") or {}).get("downloadUrl")
        if not dl_url:
            log("SaveTube /download returned empty downloadUrl")
            return None

        final_file = output_dir / f"{clean_id}_OneForAllHub.{ext}"
        if download_stream_url(dl_url, final_file, proxy=None) and final_file.exists() and final_file.stat().st_size > 1000:
            log(f"SUCCESS with SaveTube CDN fallback: {final_file.name} ({final_file.stat().st_size} bytes)")
            return final_file
    except Exception as ste:
        log(f"SaveTube fallback note: {ste}")
    return None

def download_youtube(url: str, output_dir: Path, fmt: str, proxy: Optional[str] = None) -> Optional[Path]:
    """
    Rock-solid multi-strategy YouTube engine supporting 1080p, 720p, 480p, 360p and 192k MP3.
    Bypasses YouTube SABR-only streaming experiment and datacenter bot checks with isolated cookie copies,
    WARP + Cookies, VisionOS/Android client rotation, and proxy-aware pytubefix fallback.
    """
    clean_id = extract_media_id(url)
    report_progress(50, "Connecting to YouTube & extracting streams...")
    is_audio = fmt == "audio-mp3"
    target_ext = "mp3" if is_audio else "mp4"
    final_output_file = output_dir / f"{clean_id}_OneForAllHub.{target_ext}"

    env_with_proxy = {**os.environ}
    if proxy:
        env_with_proxy["HTTP_PROXY"] = proxy
        env_with_proxy["HTTPS_PROXY"] = proxy
        env_with_proxy["http_proxy"] = proxy
        env_with_proxy["https_proxy"] = proxy
        env_with_proxy["NO_PROXY"] = "127.0.0.1,localhost"
        env_with_proxy["no_proxy"] = "127.0.0.1,localhost"

    # Select height cap and format filter
    if fmt == "video-1080p":
        v_filter = "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b/18/best"
    elif fmt == "video-720p":
        v_filter = "bv*[height<=720]+ba/b[height<=720]/bv*+ba/b/18/best"
    elif fmt == "video-480p":
        v_filter = "bv*[height<=480]+ba/b[height<=480]/bv*+ba/b/18/best"
    elif fmt == "video-360p":
        v_filter = "18/bv*[height<=360]+ba/b[height<=360]/b[height<=360]/best"
    elif is_audio:
        v_filter = "ba/b"
    else:
        v_filter = "bv*+ba/b/18/best"

    has_cookies = _find_master_cookies_file() is not None

    # Tuple format: (plan_name, use_cookies, extra_args, use_proxy)
    bgutil_arg = "youtubepot-bgutilhttp:base_url=http://127.0.0.1:4416"
    plans = []
    if proxy:
        plans.append(("WARP + BGUtil PO-Token (mweb/web)", False, ["--extractor-args", "youtube:player_client=mweb,web,web_embedded", "--extractor-args", bgutil_arg], True))
        plans.append(("WARP + BGUtil PO-Token (tv_embedded/safari)", False, ["--extractor-args", "youtube:player_client=tv_embedded,web_safari", "--extractor-args", bgutil_arg], True))
        if has_cookies:
            plans.append(("WARP + BGUtil + Cookies", True, ["--extractor-args", "youtube:player_client=web,mweb", "--extractor-args", bgutil_arg], True))
        plans.append(("WARP Android/VisionOS client", False, ["--extractor-args", "youtube:player_client=default,-web,android", "--extractor-args", "youtube:player_skip=configs"], True))

    # Native direct connection fallbacks
    plans.append(("Direct + BGUtil PO-Token (mweb/web)", False, ["--extractor-args", "youtube:player_client=mweb,web,web_embedded", "--extractor-args", bgutil_arg], False))
    plans.append(("Direct + BGUtil PO-Token (tv_embedded/safari)", False, ["--extractor-args", "youtube:player_client=tv_embedded,web_safari", "--extractor-args", bgutil_arg], False))
    if has_cookies:
        plans.append(("Direct + BGUtil + Cookies", True, ["--extractor-args", "youtube:player_client=web,mweb", "--extractor-args", bgutil_arg], False))
    plans.append(("Direct Android/VisionOS client", False, ["--extractor-args", "youtube:player_client=default,-web,android", "--extractor-args", "youtube:player_skip=configs"], False))

    for plan_name, use_cookies, extra_args, use_proxy in plans:
        log(f"YouTube Engine trying: {plan_name} (proxy={use_proxy}, cookies={use_cookies})...")
        report_progress(53, f"Fetching YouTube stream ({plan_name})...")
        c_args = get_cookie_args(url) if use_cookies else []
        cmd = [
            *get_ytdlp_cmd(),
            "--no-playlist",
            "--force-ipv4",
            "--socket-timeout", "15",
            "--retries", "2",
            "--fragment-retries", "3",
            "--file-access-retries", "2",
            "--http-chunk-size", "10M",
            "--paths", str(output_dir),
            "-o", f"{clean_id}_OneForAllHub.%(ext)s"
        ] + c_args

        if extra_args and "-f" in extra_args:
            cmd.extend(extra_args)
        elif is_audio:
            cmd.extend(["-f", "ba/b", "-x", "--audio-format", "mp3", "--audio-quality", "0"])
        else:
            cmd.extend(["-f", v_filter, "--merge-output-format", "mp4"])

        if extra_args and "-f" not in extra_args:
            cmd.extend(extra_args)

        plan_env = env_with_proxy if (use_proxy and proxy) else {k: v for k, v in os.environ.items() if not k.lower().endswith("proxy")}
        if use_proxy and proxy:
            cmd.extend(["--proxy", proxy])

        cmd.append(url)

        try:
            code, out_str = run_ytdlp_with_progress(cmd, plan_env, timeout=40, stage_label="Downloading YouTube stream")
            log(f"Plan output summary: {out_str[-250:]}")
            f = get_latest_file(output_dir, prefer_video=not is_audio)
            if f and f.stat().st_size > 1000:
                log(f"SUCCESS with {plan_name}: {f.name} ({f.stat().st_size} bytes)")
                return f
        except Exception as pe:
            log(f"Plan {plan_name} note: {pe}")

    # Fallback: Native pytubefix v11 engine (WEB/MWEB auto-PO-token + adaptive HD muxing)
    log("Invoking native pytubefix fallback engine (WEB/MWEB Auto-PO-Token + Adaptive Mux)...")
    report_progress(60, "Downloading via high-speed native pytubefix engine...")
    try:
        from pytubefix import YouTube
        pt_proxies = {"http": proxy, "https": proxy} if proxy else None
        pt_clients = (
            [("WEB", pt_proxies), ("MWEB", pt_proxies), ("WEB", None), ("MWEB", None), ("ANDROID", pt_proxies), ("IOS", pt_proxies)]
            if proxy else
            [("WEB", None), ("MWEB", None), ("ANDROID", None), ("IOS", None)]
        )
        max_h = 1080 if fmt in ("video-1080p", "video-best") else (720 if fmt == "video-720p" else (480 if fmt == "video-480p" else 360))
        for pt_client, pt_p in pt_clients:
            try:
                yt = YouTube(url, client=pt_client, proxies=pt_p) if pt_p else YouTube(url, client=pt_client)
                if is_audio:
                    audio_stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
                    if audio_stream:
                        temp_raw = output_dir / f"ptfix_raw_{clean_id}"
                        audio_stream.download(output_path=str(output_dir), filename=temp_raw.name)
                        subprocess.run([
                            "ffmpeg", "-y", "-i", str(temp_raw),
                            "-vn", "-ar", "44100", "-ac", "2", "-b:a", "192k",
                            str(final_output_file)
                        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        try: temp_raw.unlink()
                        except Exception: pass
                        if final_output_file.exists() and final_output_file.stat().st_size > 1000:
                            log(f"SUCCESS with pytubefix ({pt_client}, Audio MP3): {final_output_file.name}")
                            return final_output_file
                else:
                    adap_candidates = [
                        s for s in yt.streams.filter(adaptive=True, only_video=True, file_extension='mp4').order_by('resolution').desc()
                        if s.resolution and s.resolution.rstrip('p').isdigit() and int(s.resolution.rstrip('p')) <= max_h
                    ]
                    aud_s = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
                    if adap_candidates and aud_s:
                        v_tmp = output_dir / f"pt_v_{clean_id}.mp4"
                        a_tmp = output_dir / f"pt_a_{clean_id}.m4a"
                        adap_candidates[0].download(output_path=str(output_dir), filename=v_tmp.name)
                        aud_s.download(output_path=str(output_dir), filename=a_tmp.name)
                        subprocess.run([
                            "ffmpeg", "-y", "-i", str(v_tmp), "-i", str(a_tmp),
                            "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart",
                            str(final_output_file)
                        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        for tf in (v_tmp, a_tmp):
                            try:
                                if tf.exists(): tf.unlink()
                            except Exception: pass
                        if final_output_file.exists() and final_output_file.stat().st_size > 1000:
                            log(f"SUCCESS with pytubefix ({pt_client}, Adaptive {adap_candidates[0].resolution}): {final_output_file.name}")
                            return final_output_file

                    video_stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
                    if not video_stream:
                        video_stream = yt.streams.filter(file_extension='mp4').order_by('resolution').desc().first()
                    if video_stream:
                        out_path = video_stream.download(output_path=str(output_dir), filename=f"{clean_id}_OneForAllHub.mp4")
                        f = Path(out_path)
                        if f.exists() and f.stat().st_size > 1000:
                            log(f"SUCCESS with pytubefix ({pt_client}, Video MP4): {f.name}")
                            return f
            except Exception as ce:
                log(f"pytubefix ({pt_client}, proxy={bool(pt_p)}) note: {ce}")
    except Exception as pfe:
        log(f"pytubefix engine note: {pfe}")

    # Layer 3 Fallback: SaveTube External CDN API
    st_file = download_youtube_savetube(url, output_dir, fmt, clean_id)
    if st_file and st_file.exists() and st_file.stat().st_size > 1000:
        return st_file

    return None

# =====================================================================
# 4.5. Pinterest Dedicated Engine (Cobalt Shortener + High-Res Images & HD Videos)
# =====================================================================
def download_pinterest(url: str, output_dir: Path, fmt: str, proxy: Optional[str] = None) -> Optional[Path]:
    log("Attempting native Pinterest HD/4K extractor (Cobalt-enhanced)...")
    url = sanitize_url(url)
    report_progress(50, "Resolving original Pinterest media asset...")
    clean_id = extract_media_id(url)
    try:
        headers = {
            'User-Agent': GENERIC_CHROME_UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5'
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            final_url = resp.geturl()
            html = resp.read().decode('utf-8', errors='ignore')

        if re.search(r'"__typename"\s*:\s*"PinNotFound"', html):
            set_error_reason("unavailable", "This Pinterest Pin was not found or deleted.")
            return None

        m_id = re.search(r'/pin/(?:[^/]+--)?([0-9]+)', final_url) or re.search(r'/pin/(?:[^/]+--)?([0-9]+)', url)
        pin_id = m_id.group(1) if m_id else clean_id

        # 1. Check for Video (Cobalt videoRegex + og:video)
        vid_meta = re.search(r'<meta[^>]+(?:property="og:video"|name="twitter:player:stream")[^>]+content="([^"]+)"', html)
        if not vid_meta:
            vid_meta = re.search(r'<meta[^>]+content="([^"]+)"[^>]+(?:property="og:video"|name="twitter:player:stream")', html)
        vid_json = re.search(r'https://v1\.pinimg\.com/videos/[^"\'\s<>\)]+\.mp4', html)
        video_url = vid_meta.group(1) if vid_meta else (vid_json.group(0) if vid_json else None)

        if video_url:
            log(f"Found Pinterest video: {video_url}")
            dest = output_dir / f"{pin_id}_OneForAllHub.mp4"
            if download_stream_url(video_url, dest):
                log(f"Successfully downloaded Pinterest video: {dest.name} ({dest.stat().st_size} bytes)")
                return dest

        # 2. Check for Image / GIF
        img_m = re.search(r'"(?:images_orig|orig)"\s*:\s*\{[^}]*"url"\s*:\s*"([^"]+)"', html)
        if not img_m:
            img_m = re.search(r'"url"\s*:\s*"(https://i\.pinimg\.com/originals/[^"]+)"', html)

        img_url = None
        if img_m:
            img_url = img_m.group(1).replace(r'\/', '/')
        else:
            preload_m = re.search(r'<link[^>]+id="pin-image-preload"[^>]+href="([^"]+)"', html)
            if not preload_m:
                preload_m = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
            if not preload_m:
                preload_m = re.search(r'src="(https://i\.pinimg\.com/[^"]+\.(?:jpg|png|gif))"', html)
            if preload_m:
                raw_img = preload_m.group(1).replace(r'\/', '/')
                img_url = re.sub(r'/(?:736x|564x|474x|236x|1200x)/', '/originals/', raw_img)

        if img_url:
            log(f"Found Pinterest image: {img_url}")
            ext = 'png' if '.png' in img_url.lower() else ('webp' if '.webp' in img_url.lower() else ('gif' if '.gif' in img_url.lower() else 'jpg'))
            dest = output_dir / f"{pin_id}_OneForAllHub.{ext}"
            try:
                i_req = urllib.request.Request(img_url, headers={'User-Agent': GENERIC_CHROME_UA})
                with urllib.request.urlopen(i_req, timeout=20) as i_resp, open(dest, 'wb') as f:
                    f.write(i_resp.read())
            except urllib.error.HTTPError as e:
                if e.code in (403, 404):
                    alt_url = re.sub(r'\.jpg$', '.png', img_url) if ext == 'jpg' else re.sub(r'\.png$', '.jpg', img_url)
                    alt_ext = 'png' if ext == 'jpg' else 'jpg'
                    dest = output_dir / f"{pin_id}_OneForAllHub.{alt_ext}"
                    i_req = urllib.request.Request(alt_url, headers={'User-Agent': GENERIC_CHROME_UA})
                    with urllib.request.urlopen(i_req, timeout=20) as i_resp, open(dest, 'wb') as f:
                        f.write(i_resp.read())
                else:
                    raise
            if dest.exists() and dest.stat().st_size > 1000:
                log(f"Successfully downloaded Pinterest image: {dest.name} ({dest.stat().st_size} bytes)")
                return dest
    except Exception as e:
        log(f"Pinterest extractor note: {e}")
    return None

# =====================================================================
# 4.6. Facebook Dedicated Engine (Cobalt facebook.js + yt-dlp Fallback)
# =====================================================================
def download_facebook(url: str, output_dir: Path, fmt: str, proxy: Optional[str] = None) -> Optional[Path]:
    log("Attempting Facebook download via Cobalt Facebook Engine...")
    report_progress(50, "Extracting Facebook HD video stream...")
    url = sanitize_url(url)
    clean_id = extract_media_id(url)
    is_audio = fmt == "audio-mp3"
    final_file = output_dir / f"{clean_id}_OneForAllHub.{'mp3' if is_audio else 'mp4'}"

    fb_headers = {
        "User-Agent": GENERIC_CHROME_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
    }
    for use_p in ([proxy, None] if proxy else [None]):
        try:
            _, html = _ig_http_get(url, fb_headers, proxy=use_p, timeout=15)
            candidates = []
            for key in ["browser_native_hd_url", "playable_url_quality_hd", "browser_native_sd_url", "playable_url"]:
                m = re.search(rf'"{key}"\s*:\s*(".*?")', html)
                if m:
                    try:
                        u = json.loads(m.group(1))
                        if u and u.startswith("http"):
                            candidates.append(u)
                    except Exception:
                        pass
            if candidates:
                chosen = candidates[0]
                log(f"Cobalt Facebook resolved stream: {chosen[:80]}...")
                temp_mp4 = output_dir / f"temp_{clean_id}.mp4" if is_audio else final_file
                if download_stream_url(chosen, temp_mp4, proxy=use_p):
                    if is_audio:
                        subprocess.run([
                            "ffmpeg", "-y", "-threads", "0", "-i", str(temp_mp4),
                            "-vn", "-ar", "44100", "-ac", "2", "-b:a", "192k",
                            str(final_file)
                        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        try: temp_mp4.unlink()
                        except Exception: pass
                    if final_file.exists() and final_file.stat().st_size > 1000:
                        return final_file
        except Exception as fe:
            log(f"Cobalt Facebook note (proxy={bool(use_p)}): {fe}")
    return None

# =====================================================================
# 4.7. Reddit Dedicated Engine (Cobalt reddit.js DASH Video + Audio Mux)
# =====================================================================
def download_reddit(url: str, output_dir: Path, fmt: str, proxy: Optional[str] = None) -> Optional[Path]:
    log("Attempting Reddit download via Cobalt Reddit JSON Engine...")
    report_progress(50, "Extracting Reddit video & audio tracks...")
    url = sanitize_url(url)
    clean_id = extract_media_id(url)
    is_audio = fmt == "audio-mp3"
    m = re.search(r'/comments/([a-zA-Z0-9]+)', url)
    if not m:
        return None
    post_id = m.group(1)
    try:
        hdrs = {"User-Agent": GENERIC_CHROME_UA, "Accept": "application/json"}
        _, txt = _ig_http_get(f"https://www.reddit.com/comments/{post_id}.json", hdrs, proxy=proxy, timeout=12)
        arr = json.loads(txt)
        if not isinstance(arr, list) or not arr:
            return None
        post = arr[0]["data"]["children"][0]["data"]
        rvid = (post.get("secure_media") or {}).get("reddit_video")
        if not rvid or not rvid.get("fallback_url"):
            return None
        vid_url = rvid["fallback_url"].split("?")[0]
        v_tmp = output_dir / f"temp_v_{clean_id}.mp4"
        a_tmp = output_dir / f"temp_a_{clean_id}.mp4"
        final_file = output_dir / f"{clean_id}_OneForAllHub.{'mp3' if is_audio else 'mp4'}"

        if not download_stream_url(vid_url, v_tmp, proxy=proxy):
            return None

        # Cobalt audio track discovery (_audio.mp4 / _AUDIO_128.mp4 / DASH_audio.mp4)
        base_prefix = vid_url.split("_")[0] if ".mp4" in vid_url else vid_url.split("DASH")[0]
        audio_ok = False
        for aud_cand in [f"{base_prefix}_audio.mp4", f"{base_prefix}_AUDIO_128.mp4", f"{vid_url.split('DASH')[0]}DASH_audio.mp4"]:
            if download_stream_url(aud_cand, a_tmp, proxy=proxy):
                audio_ok = True
                break

        if is_audio:
            src_a = a_tmp if audio_ok else v_tmp
            subprocess.run([
                "ffmpeg", "-y", "-i", str(src_a), "-vn", "-ar", "44100", "-ac", "2", "-b:a", "192k", str(final_file)
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif audio_ok:
            subprocess.run([
                "ffmpeg", "-y", "-i", str(v_tmp), "-i", str(a_tmp), "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart", str(final_file)
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            v_tmp.rename(final_file)

        for t in (v_tmp, a_tmp):
            if t.exists() and t != final_file:
                try: t.unlink()
                except Exception: pass

        if final_file.exists() and final_file.stat().st_size > 1000:
            log(f"Cobalt Reddit SUCCESS: {final_file.name}")
            return final_file
    except Exception as re_err:
        log(f"Cobalt Reddit note: {re_err}")

    # Tier 2: vxreddit.com mirror (bypasses Reddit 403 datacenter IP blocks cleanly)
    try:
        import html as _html
        vx_url = f"https://vxreddit.com/comments/{post_id}"
        log(f"Trying Reddit Tier 2 (vxreddit mirror): {vx_url}")
        req = urllib.request.Request(vx_url, headers={"User-Agent": "TelegramBot (like TwitterBot)"})
        with urllib.request.urlopen(req, timeout=15) as r:
            page = r.read().decode("utf-8", errors="replace")
        vids = re.findall(r'property="og:video(?::secure_url)?"\s+content="([^"]+)"', page)
        if vids:
            vid_url = _html.unescape(vids[0])
            final_file = output_dir / f"{clean_id}_OneForAllHub.{'mp3' if is_audio else 'mp4'}"
            tmp_vid = output_dir / f"temp_vx_{clean_id}.mp4"
            if download_stream_url(vid_url, tmp_vid, proxy=None) or (proxy and download_stream_url(vid_url, tmp_vid, proxy=proxy)):
                if is_audio:
                    subprocess.run([
                        "ffmpeg", "-y", "-i", str(tmp_vid), "-vn", "-ar", "44100", "-ac", "2", "-b:a", "192k", str(final_file)
                    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    try: tmp_vid.unlink()
                    except Exception: pass
                else:
                    tmp_vid.rename(final_file)
                if final_file.exists() and final_file.stat().st_size > 1000:
                    log(f"Reddit Tier 2 (vxreddit) SUCCESS: {final_file.name} ({final_file.stat().st_size} bytes)")
                    return final_file
    except Exception as vx_err:
        log(f"Reddit Tier 2 (vxreddit) note: {vx_err}")
    return None

# =====================================================================
# 4.8. Spotify Dedicated Engine (Zero-Auth Embed Metadata + Duration-Matched YT/SoundCloud/pytubefix Audio + ID3 & Cover Art)
# =====================================================================
def fetch_spotify_metadata(url: str) -> Optional[dict]:
    """Resolve Spotify track/album/playlist/episode title, artist, duration, and 640x640 cover art without API keys."""
    m = re.search(r'spotify\.com/(?:intl-[a-z-]+/)?(track|album|playlist|episode)/([a-zA-Z0-9]+)', url)
    if not m:
        return None
    kind, item_id = m.group(1), m.group(2)
    headers = {"User-Agent": GENERIC_CHROME_UA, "Accept-Language": "en-US,en;q=0.9"}

    # Method 1: Official Spotify Embed __NEXT_DATA__ (< 300ms, full structured metadata)
    try:
        req = urllib.request.Request(f"https://open.spotify.com/embed/{kind}/{item_id}", headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        nd_m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
        if nd_m:
            nd = json.loads(nd_m.group(1))
            ent = (((nd.get("props") or {}).get("pageProps") or {}).get("state") or {}).get("data", {}).get("entity") or {}
            imgs = (ent.get("visualIdentity") or {}).get("image") or []
            cover = imgs[0].get("url") if imgs else ""
            if kind in ("album", "playlist") and ent.get("trackList"):
                t0 = ent["trackList"][0]
                title = t0.get("title") or ent.get("name") or ""
                artist = t0.get("subtitle") or ""
                dur_sec = round((t0.get("duration") or 0) / 1000)
                if title:
                    return {"id": item_id, "kind": kind, "title": title, "artist": artist, "duration_sec": dur_sec, "cover": cover}
            else:
                title = ent.get("name") or ent.get("title") or ""
                artists = [a.get("name") for a in (ent.get("artists") or []) if a.get("name")]
                artist = ", ".join(artists) or ent.get("subtitle") or ""
                dur_sec = round((ent.get("duration") or 0) / 1000)
                if title:
                    return {"id": item_id, "kind": kind, "title": title, "artist": artist, "duration_sec": dur_sec, "cover": cover}
    except Exception as se:
        log(f"Spotify Embed metadata note: {se}")

    # Method 2: Official Spotify oEmbed fallback
    try:
        oe_url = f"https://open.spotify.com/oembed?url={urllib.parse.quote(url)}"
        req = urllib.request.Request(oe_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            oe = json.loads(resp.read().decode("utf-8", errors="ignore"))
        if oe.get("title"):
            return {
                "id": item_id,
                "kind": kind,
                "title": oe["title"],
                "artist": oe.get("author_name") or "",
                "duration_sec": 0,
                "cover": oe.get("thumbnail_url") or "",
            }
    except Exception as oe_err:
        log(f"Spotify oEmbed note: {oe_err}")
    return None

def download_spotify(url: str, output_dir: Path, fmt: str, proxy: Optional[str] = None) -> Optional[Path]:
    """Download full-length studio 192kbps MP3 for Spotify links with official cover art and ID3 metadata."""
    log("Attempting Spotify download via Zero-Auth Metadata + Multi-Source Audio Engine...")
    report_progress(50, "🎵 Resolving Spotify track metadata & album cover art...")
    url = sanitize_url(url)
    clean_id = extract_media_id(url)
    final_mp3 = output_dir / f"{clean_id}_OneForAllHub.mp3"

    meta = fetch_spotify_metadata(url)
    if not meta or not meta.get("title"):
        log("Could not resolve Spotify track metadata.")
        set_error_reason("unavailable", "Could not find this Spotify track. Please verify the link is public.")
        return None

    title = meta["title"].strip()
    artist = (meta.get("artist") or "").strip()
    dur_sec = int(meta.get("duration_sec") or 0)
    cover_url = meta.get("cover") or ""
    query = f"{artist} - {title}" if artist else title
    log(f"Spotify Metadata Resolved: '{title}' by '{artist}' ({dur_sec}s)")

    # Persist Spotify metadata for notify_telegram & post-processing
    try:
        with open("/tmp/spotify_meta.json", "w", encoding="utf-8") as sf:
            json.dump({"title": title, "artist": artist, "duration": dur_sec, "cover": cover_url}, sf)
    except Exception:
        pass

    # Download official high-res Spotify album cover art thumbnail immediately
    thumb_path = output_dir / f"{clean_id}_OneForAllHub_thumb.jpg"
    if cover_url:
        try:
            c_req = urllib.request.Request(cover_url, headers={"User-Agent": GENERIC_CHROME_UA})
            with urllib.request.urlopen(c_req, timeout=10) as cr:
                thumb_path.write_bytes(cr.read())
            log(f"Downloaded Spotify album cover art: {thumb_path.stat().st_size} bytes")
        except Exception as ce:
            log(f"Spotify cover art note: {ce}")

    env_with_proxy = {**os.environ}
    if proxy:
        env_with_proxy["HTTP_PROXY"] = proxy
        env_with_proxy["HTTPS_PROXY"] = proxy
        env_with_proxy["http_proxy"] = proxy
        env_with_proxy["https_proxy"] = proxy
        env_with_proxy["NO_PROXY"] = "127.0.0.1,localhost"
        env_with_proxy["no_proxy"] = "127.0.0.1,localhost"

    has_cookies = _find_master_cookies_file() is not None
    dur_filter = []
    if dur_sec > 20:
        min_d = max(15, dur_sec - 45)
        max_d = dur_sec + 65
        dur_filter = ["--match-filter", f"duration >= {min_d} & duration <= {max_d}"]

    search_plans = []
    # Tier 1: YouTube Audio Search (BGUtil PO-Token + WARP + Direct + Authenticated Cookies)
    yt_query = f"ytsearch3:{query} audio"
    bgutil_arg = "youtubepot-bgutilhttp:base_url=http://127.0.0.1:4416"
    if proxy:
        search_plans.append(("WARP BGUtil PO-Token YouTube Search", yt_query, False, ["--extractor-args", "youtube:player_client=mweb,web", "--extractor-args", bgutil_arg], True, True))
        search_plans.append(("WARP YouTube Audio Search", yt_query, False, ["--extractor-args", "youtube:player_client=default,-web,android", "--extractor-args", "youtube:player_skip=configs"], True, True))
        if has_cookies:
            search_plans.append(("WARP Authenticated YouTube Search", yt_query, True, ["--extractor-args", "youtube:player_client=default,-android,-ios"], True, True))
    search_plans.append(("Direct BGUtil PO-Token YouTube Search", yt_query, False, ["--extractor-args", "youtube:player_client=mweb,web", "--extractor-args", bgutil_arg], False, True))
    search_plans.append(("Direct YouTube Audio Search", yt_query, False, ["--extractor-args", "youtube:player_client=default,-web,android", "--extractor-args", "youtube:player_skip=configs"], False, True))
    if has_cookies:
        search_plans.append(("Direct Authenticated YouTube Search", yt_query, True, ["--extractor-args", "youtube:player_client=default,-android,-ios"], False, True))
    # Tier 2: SoundCloud Search Fallback (zero YouTube bot checks!)
    search_plans.append(("SoundCloud Audio Search", f"scsearch2:{query}", False, [], bool(proxy), False))

    raw_audio_file = None
    for plan_name, search_expr, use_cookies, extra_args, use_proxy, use_dur_filter in search_plans:
        log(f"Spotify Engine trying: {plan_name} -> {search_expr}")
        report_progress(56, f"🎵 Matching studio audio ({title[:28]})...")
        c_args = get_cookie_args("https://www.youtube.com/watch?v=x") if use_cookies else []
        cmd = [
            *get_ytdlp_cmd(),
            "--max-downloads", "1",
            "--force-ipv4",
            "--socket-timeout", "15",
            "--retries", "2",
            "--fragment-retries", "3",
            "--paths", str(output_dir),
            "-o", f"sp_raw_{clean_id}.%(ext)s",
            "-f", "ba/b",
        ] + c_args + extra_args
        if use_dur_filter and dur_filter:
            cmd.extend(dur_filter)
        plan_env = env_with_proxy if (use_proxy and proxy) else {k: v for k, v in os.environ.items() if not k.lower().endswith("proxy")}
        if use_proxy and proxy:
            cmd.extend(["--proxy", proxy])
        cmd.append(search_expr)

        try:
            _, out_s = run_ytdlp_with_progress(cmd, plan_env, timeout=40, stage_label="Downloading Spotify audio track")
            log(f"Spotify plan output: {out_s[-220:]}")
            candidates = [f for f in output_dir.glob(f"sp_raw_{clean_id}.*") if f.is_file() and not f.name.endswith(".part") and f.stat().st_size > 10000]
            if candidates:
                raw_audio_file = candidates[0]
                log(f"Spotify audio matched via {plan_name}: {raw_audio_file.name} ({raw_audio_file.stat().st_size} bytes)")
                break
        except Exception as pe:
            log(f"Spotify plan {plan_name} note: {pe}")

    # Tier 3: pytubefix Search fallback (proxy aware)
    if not raw_audio_file:
        log("Spotify Tier 3: pytubefix Search fallback...")
        try:
            from pytubefix import Search, YouTube
            s = Search(f"{query} audio")
            results = (s.videos or [])[:5]
            if results:
                chosen = results[0]
                if dur_sec > 20:
                    chosen = min(results, key=lambda v: abs((getattr(v, "length", 0) or 0) - dur_sec))
                pt_proxies = {"http": proxy, "https": proxy} if proxy else None
                yt = YouTube(chosen.watch_url, client="WEB", proxies=pt_proxies) if pt_proxies else YouTube(chosen.watch_url, client="WEB")
                stream = yt.streams.filter(only_audio=True).order_by("abr").desc().first()
                if stream:
                    dl_p = stream.download(output_path=str(output_dir), filename=f"sp_raw_{clean_id}.m4a")
                    if Path(dl_p).exists() and Path(dl_p).stat().st_size > 10000:
                        raw_audio_file = Path(dl_p)
                        log(f"Spotify pytubefix Search SUCCESS: {raw_audio_file.name}")
        except Exception as pfe:
            log(f"Spotify pytubefix Search note: {pfe}")

    if not raw_audio_file or not raw_audio_file.exists():
        return None

    # Convert to studio 192kbps MP3 with embedded ID3v2 tags (+ cover art if available)
    report_progress(82, f"🎧 Mastering 192kbps MP3 & embedding Spotify metadata...")
    try:
        ff_cmd = ["ffmpeg", "-y", "-i", str(raw_audio_file)]
        if thumb_path.exists() and thumb_path.stat().st_size > 500:
            ff_cmd.extend(["-i", str(thumb_path), "-map", "0:a:0", "-map", "1:v:0", "-c:v", "mjpeg", "-disposition:v", "attached_pic"])
        else:
            ff_cmd.extend(["-vn"])
        ff_cmd.extend([
            "-c:a", "libmp3lame", "-ar", "44100", "-ac", "2", "-b:a", "192k",
            "-id3v2_version", "3",
            "-metadata", f"title={title}",
            "-metadata", f"artist={artist or 'OneForAllHub'}",
            "-metadata", "comment=Downloaded via @OneForAllDownloaderBot (@OneForAllHub)",
            str(final_mp3),
        ])
        subprocess.run(ff_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45)
        if final_mp3.exists() and final_mp3.stat().st_size > 10000:
            try: raw_audio_file.unlink()
            except Exception: pass
            log(f"Spotify Studio MP3 READY: {final_mp3.name} ({final_mp3.stat().st_size} bytes)")
            return final_mp3
    except Exception as fe:
        log(f"Spotify FFmpeg mastering note: {fe}")

    return raw_audio_file

def download_general_ytdlp(url: str, output_dir: Path, fmt: str, proxy: Optional[str] = None) -> Optional[Path]:
    log(f"Attempting general yt-dlp download (format={fmt})...")
    report_progress(50, "Extracting media streams via 10Gbps engine...")
    clean_id = extract_media_id(url)
    is_audio = fmt == "audio-mp3"
    cookie_args = get_cookie_args(url)

    def build_cmd(use_cookies: bool = True):
        c = [
            *get_ytdlp_cmd(),
            "--verbose",
            "--no-playlist",
            "--retries", "3",
            "--fragment-retries", "3",
            "--file-access-retries", "2",
            "--socket-timeout", "15",
            "--http-chunk-size", "10M",
            "--paths", str(output_dir),
            "-o", f"{clean_id}_OneForAllHub.%(ext)s"
        ]
        if "youtube.com" in url or "youtu.be" in url:
            c.extend(["--extractor-args", "youtube:player_client=default,-web,android", "--extractor-args", "youtube:player_skip=configs"])
        if use_cookies and cookie_args:
            c.extend(cookie_args)
        if is_audio:
            c.extend(["-f", "ba/b", "-x", "--audio-format", "mp3", "--audio-quality", "0"])
        elif fmt == "video-1080p":
            c.extend(["-f", "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b/18/best", "--merge-output-format", "mp4"])
        elif fmt == "video-720p":
            c.extend(["-f", "bv*[height<=720]+ba/b[height<=720]/bv*+ba/b/18/best", "--merge-output-format", "mp4"])
        elif fmt == "video-360p":
            c.extend(["-f", "18/bv*[height<=360]+ba/b[height<=360]/b[height<=360]/best", "--merge-output-format", "mp4"])
        else:
            c.extend(["-f", "bv*+ba/b/18/best", "--merge-output-format", "mp4"])
        c.append(url)
        return c

    env_with_proxy = {**os.environ}
    if proxy:
        env_with_proxy["HTTP_PROXY"] = proxy
        env_with_proxy["HTTPS_PROXY"] = proxy
        env_with_proxy["http_proxy"] = proxy
        env_with_proxy["https_proxy"] = proxy
        env_with_proxy["NO_PROXY"] = "127.0.0.1,localhost"
        env_with_proxy["no_proxy"] = "127.0.0.1,localhost"

    for attempt, use_c in enumerate([True, False] if cookie_args else [False]):
        log(f"Attempting general yt-dlp download (attempt={attempt+1}, use_cookies={use_c})...")
        cmd = build_cmd(use_cookies=use_c)
        try:
            code, out_str = run_ytdlp_with_progress(cmd, env_with_proxy, timeout=40, stage_label="Downloading media stream")
            log("yt-dlp output summary:\n" + out_str[-400:])
            f = get_latest_file(output_dir, prefer_video=not is_audio)
            if f and f.stat().st_size > 1000:
                return f
        except Exception as e:
            log(f"General yt-dlp attempt {attempt+1} note: {e}")
    return get_latest_file(output_dir, prefer_video=not is_audio)

# =====================================================================
# Delivery & CDN Upload Handlers
# =====================================================================
def upload_github_release(file_path: Path, tag: str = "v1.0-media") -> Optional[str]:
    log(f"Uploading {file_path.name} to GitHub Releases ({tag})...")
    try:
        cmd = ["gh", "release", "upload", tag, str(file_path), "--clobber"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=90)
        if res.returncode == 0:
            link = f"https://github.com/TheHunterX/oneforall-media-downloader/releases/download/{tag}/{urllib.parse.quote(file_path.name)}"
            log(f"GitHub Releases direct link: {link}")
            return link
        else:
            log(f"gh release upload note: {res.stderr.strip()[:200]}")
    except Exception as e:
        log(f"gh release upload error: {e}")
    return None

def upload_catbox(file_path: Path) -> Optional[str]:
    log(f"Uploading {file_path.name} ({file_path.stat().st_size} bytes) to Catbox CDN...")
    try:
        cmd = ["curl", "-s", "-F", "reqtype=fileupload", "-F", f"fileToUpload=@{file_path}", "https://catbox.moe/user/api.php"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=90)
        link = res.stdout.strip()
        if link.startswith("http"):
            log(f"Catbox direct link: {link}")
            return link
    except Exception as e:
        log(f"Catbox upload error: {e}")
    return None

def upload_uguu(file_path: Path) -> Optional[str]:
    log(f"Uploading {file_path.name} ({file_path.stat().st_size} bytes) to Uguu CDN...")
    try:
        cmd = ["curl", "-s", "-F", f"files[]=@{file_path}", "https://uguu.se/upload.php"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=90)
        data = json.loads(res.stdout)
        if data.get("success") and "files" in data and len(data["files"]) > 0:
            link = data["files"][0].get("url")
            if link:
                log(f"Uguu direct link: {link}")
                return link
    except Exception as e:
        log(f"Uguu upload error: {e}")
    return None

def upload_media_cdn(file_path: Path) -> Optional[str]:
    log(f"Delivering {file_path.name} ({file_path.stat().st_size} bytes) via high-speed direct CDN...")
    rel_link = upload_github_release(file_path)
    if rel_link:
        return rel_link
    catbox_link = upload_catbox(file_path)
    if catbox_link:
        return catbox_link
    uguu_link = upload_uguu(file_path)
    if uguu_link:
        return uguu_link
    return None

def main():
    if len(sys.argv) < 2:
        print("Usage: python download.py <url> [format]")
        sys.exit(1)

    raw_url = sys.argv[1].strip()
    fmt = sys.argv[2].strip() if len(sys.argv) > 2 else "video-720p"
    url = sanitize_url(raw_url)
    if "spotify.com" in url or "spotify.link" in url or "spoti.fi" in url:
        fmt = "audio-mp3"
    is_audio = fmt == "audio-mp3"
    log(f"Final target URL: {url} | Format: {fmt}")

    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    # Clear out leftover files
    for item in output_dir.glob("*"):
        if item.is_file():
            try:
                item.unlink()
            except Exception:
                pass

    # Detect Cloudflare WARP proxy
    warp_proxy = check_warp_proxy()

    target_file = None

    # Step 1: TikTok High-Speed Direct Engine (TikWM + Cobalt Rehydration)
    if "tiktok.com" in url:
        target_file = download_tiktok_tikwm(url, output_dir, is_audio=is_audio, proxy=warp_proxy)

    # Step 2: Twitter / X Dedicated Engine (FxTwitter + Cobalt Syndication + Twitsave)
    if (not target_file or not target_file.exists()) and ("twitter.com" in url or "x.com" in url):
        target_file = download_twitter(url, output_dir, fmt, proxy=warp_proxy)

    # Step 3: Instagram Dedicated Cobalt Engine (Embed + PR#1619 Web API + Mobile Liger + Polaris GQL + Stories + yt-dlp)
    if (not target_file or not target_file.exists()) and ("instagram.com" in url):
        target_file = download_instagram(url, output_dir, fmt, proxy=warp_proxy)

    # Step 4: YouTube Multi-Tier Engine (WARP + Cookies + VisionOS/Android + pytubefix)
    if (not target_file or not target_file.exists()) and ("youtube.com" in url or "youtu.be" in url):
        target_file = download_youtube(url, output_dir, fmt, proxy=warp_proxy)

    # Step 4.5: Pinterest Dedicated Engine (Cobalt Shortener + High-Res Images & HD Videos)
    if (not target_file or not target_file.exists()) and ("pinterest." in url or "pin.it" in url):
        target_file = download_pinterest(url, output_dir, fmt, proxy=warp_proxy)

    # Step 4.6: Facebook Dedicated Engine (Cobalt facebook.js)
    if (not target_file or not target_file.exists()) and ("facebook.com" in url or "fb.watch" in url):
        target_file = download_facebook(url, output_dir, fmt, proxy=warp_proxy)

    # Step 4.7: Reddit Dedicated Engine (Cobalt reddit.js)
    if (not target_file or not target_file.exists()) and ("reddit.com" in url or "v.redd.it" in url):
        target_file = download_reddit(url, output_dir, fmt, proxy=warp_proxy)

    # Step 4.8: Spotify Dedicated Engine (Zero-Auth Embed Metadata + Multi-Source Audio + ID3/Cover)
    if (not target_file or not target_file.exists()) and ("spotify.com" in url or "spotify.link" in url or "spoti.fi" in url):
        target_file = download_spotify(url, output_dir, fmt, proxy=warp_proxy)

    # Step 5: General yt-dlp Engine (SoundCloud, Vimeo, Twitch, Dailymotion, etc.)
    if not target_file or not target_file.exists() or target_file.stat().st_size == 0:
        target_file = download_general_ytdlp(url, output_dir, fmt, proxy=warp_proxy)

    if not target_file or not target_file.exists() or target_file.stat().st_size < 1000:
        log("ERROR: All download engines failed to retrieve this media link.")
        write_state("error", 0, "Download engines failed")
        sys.exit(1)

    log(f"SUCCESS: Downloaded file {target_file.name} ({target_file.stat().st_size} bytes)")

    # Post-processing: Guarantee format integrity, web streaming, and extract metadata
    duration_sec = 0
    width = 0
    height = 0
    actual_res = ""
    clean_id = extract_media_id(url)

    if target_file.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
        # High-resolution image asset (Pinterest, etc.)
        log(f"High-resolution image asset detected: {target_file.name} ({target_file.stat().st_size} bytes)")
        report_progress(85, "Finalizing high-resolution image asset...")
        try:
            cmd_dim = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", str(target_file)]
            res_dim = subprocess.run(cmd_dim, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            if res_dim.returncode == 0 and res_dim.stdout.strip():
                parts = res_dim.stdout.strip().split("x")
                if len(parts) == 2:
                    width = int(parts[0])
                    height = int(parts[1])
                    actual_res = f"{width}x{height}"
                    log(f"Verified image dimensions: {actual_res}")
        except Exception:
            pass
    elif is_audio:
        # Guarantee genuine MP3 container without double extensions (e.g. .mp4.mp3)
        mp3_file = target_file.parent / f"{clean_id}_OneForAllHub.mp3"

        if target_file.suffix.lower() != ".mp3" or target_file != mp3_file:
            log(f"Converting {target_file.name} to standard 192kbps MP3 via FFmpeg: {mp3_file.name}...")
            report_progress(82, "Converting audio track to pure 192kbps MP3...")
            temp_mp3 = target_file.parent / f"conv_{clean_id}.mp3"
            try:
                res = subprocess.run([
                    "ffmpeg", "-y", "-i", str(target_file),
                    "-vn", "-ar", "44100", "-ac", "2", "-b:a", "192k",
                    str(temp_mp3)
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if temp_mp3.exists() and temp_mp3.stat().st_size > 1000:
                    if target_file.exists():
                        try: target_file.unlink()
                        except Exception: pass
                    if mp3_file.exists():
                        try: mp3_file.unlink()
                        except Exception: pass
                    temp_mp3.rename(mp3_file)
                    target_file = mp3_file
                    log(f"Audio converted successfully: {target_file.name} ({target_file.stat().st_size} bytes)")
            except Exception as fe:
                log(f"FFmpeg audio conversion note: {fe}")
        try:
            cmd_dur = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(target_file)]
            res_dur = subprocess.run(cmd_dur, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            if res_dur.returncode == 0 and res_dur.stdout.strip():
                duration_sec = int(float(res_dur.stdout.strip()))
        except Exception:
            pass
    else:
        # Guarantee web-streamable MP4 with faststart (moov atom at front)
        report_progress(82, "Optimizing MP4 container for instant Telegram video streaming...")
        faststart_file = target_file.parent / f"fs_{clean_id}.mp4"
        try:
            res = subprocess.run([
                "ffmpeg", "-y", "-i", str(target_file),
                "-c", "copy", "-movflags", "+faststart",
                str(faststart_file)
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res.returncode != 0 or not faststart_file.exists() or faststart_file.stat().st_size < 1000:
                log("Stream copy failed; transcoding to H.264/AAC for full Telegram compatibility...")
                subprocess.run([
                    "ffmpeg", "-y", "-i", str(target_file),
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart",
                    str(faststart_file)
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            final_mp4 = target_file.parent / f"{clean_id}_OneForAllHub.mp4"
            if faststart_file.exists() and faststart_file.stat().st_size > 1000:
                if target_file != final_mp4 and target_file.exists():
                    try: target_file.unlink()
                    except Exception: pass
                if final_mp4.exists() and final_mp4 != faststart_file:
                    try: final_mp4.unlink()
                    except Exception: pass
                faststart_file.rename(final_mp4)
                target_file = final_mp4
                log(f"Faststart MP4 ready: {target_file.name} ({target_file.stat().st_size} bytes)")
            elif target_file != final_mp4:
                if final_mp4.exists():
                    try: final_mp4.unlink()
                    except Exception: pass
                target_file.rename(final_mp4)
                target_file = final_mp4
        except Exception as ffe:
            log(f"FFmpeg faststart note: {ffe}; keeping original downloaded media {target_file.name}")
            final_mp4 = target_file.parent / f"{clean_id}_OneForAllHub.mp4"
            if target_file != final_mp4 and not final_mp4.exists():
                try: target_file.rename(final_mp4)
                except Exception: pass
                target_file = final_mp4

        # Probe video dimensions and duration
        try:
            cmd_dur = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(target_file)]
            res_dur = subprocess.run(cmd_dur, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            if res_dur.returncode == 0 and res_dur.stdout.strip():
                duration_sec = int(float(res_dur.stdout.strip()))
        except Exception:
            pass

        try:
            cmd_dim = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", str(target_file)]
            res_dim = subprocess.run(cmd_dim, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            if res_dim.returncode == 0 and res_dim.stdout.strip():
                parts = res_dim.stdout.strip().split("x")
                if len(parts) == 2:
                    width = int(parts[0])
                    height = int(parts[1])
                    actual_res = f"{height}p ({width}x{height})"
                    log(f"Verified video dimensions: {actual_res}, duration={duration_sec}s")
        except Exception:
            pass

        # Generate crisp thumbnail preview from video frame (at 1s or middle)
        thumb_file = target_file.parent / f"{target_file.stem}_thumb.jpg"
        try:
            subprocess.run([
                "ffmpeg", "-y", "-ss", "00:00:01", "-i", str(target_file),
                "-vframes", "1", "-vf", "scale='min(480,iw)':-2", "-q:v", "3",
                str(thumb_file)
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        except Exception:
            pass

    # Extract or fetch thumbnail for audio
    if is_audio:
        thumb_file = target_file.parent / f"{target_file.stem}_thumb.jpg"
        if ("youtube.com" in url or "youtu.be" in url) and not thumb_file.exists():
            yt_id = extract_media_id(url)
            try:
                req = urllib.request.Request(f"https://i.ytimg.com/vi/{yt_id}/hqdefault.jpg", headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=5) as r:
                    thumb_file.write_bytes(r.read())
            except Exception:
                pass

    thumb_b64 = ""
    thumb_file = target_file.parent / f"{target_file.stem}_thumb.jpg"
    if thumb_file.exists() and thumb_file.stat().st_size > 200:
        try:
            thumb_b64 = base64.b64encode(thumb_file.read_bytes()).decode("ascii")
            log(f"Generated media thumbnail: {thumb_file.stat().st_size} bytes (b64 length: {len(thumb_b64)})")
        except Exception as e:
            log(f"Thumbnail encoding error: {e}")

    # Persist shared metadata for notify_telegram step
    track_title = ""
    track_artist = ""
    try:
        sp_meta_p = Path("/tmp/spotify_meta.json")
        if sp_meta_p.exists():
            sp_d = json.loads(sp_meta_p.read_text(encoding="utf-8"))
            track_title = sp_d.get("title", "")
            track_artist = sp_d.get("artist", "")
            if not duration_sec and sp_d.get("duration"):
                duration_sec = int(sp_d["duration"])
    except Exception:
        pass

    meta = {
        "filename": target_file.name,
        "filesize": target_file.stat().st_size,
        "duration": duration_sec,
        "width": width,
        "height": height,
        "actual_res": actual_res,
        "thumb_b64": thumb_b64,
        "track_title": track_title,
        "track_artist": track_artist
    }
    try:
        with open("/tmp/media_meta.json", "w", encoding="utf-8") as mf:
            json.dump(meta, mf)
        if thumb_b64:
            with open("/tmp/thumb_b64.txt", "w", encoding="utf-8") as tf:
                tf.write(thumb_b64)
    except Exception:
        pass

    # Output variables for GitHub Actions
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"filename={target_file.name}\n")
            f.write(f"filesize={target_file.stat().st_size}\n")
            f.write(f"filepath={target_file.resolve()}\n")
            f.write(f"actual_res={actual_res}\n")
            f.write(f"duration={duration_sec}\n")
            f.write(f"width={width}\n")
            f.write(f"height={height}\n")

    # Upload to CDN for direct link
    report_progress(88, "Packaging media & publishing to Edge CDN...")
    direct_link = upload_media_cdn(target_file)
    if direct_link:
        if github_output:
            with open(github_output, "a", encoding="utf-8") as f:
                f.write(f"direct_url={direct_link}\n")
        write_state("complete", 100, "Media ready! Uploading to Telegram chat...", 0)

        summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_file:
            with open(summary_file, "a", encoding="utf-8") as f:
                f.write("### 🚀 لینک مستقیم دانلود آماده شد / Direct Download Link Ready!\n\n")
                f.write(f"- **فایل / File:** `{target_file.name}`\n")
                f.write(f"- **حجم / Size:** `{target_file.stat().st_size // 1024} KB`\n")
                f.write(f"- **لینک دانلود پرسرعت / Direct Link:** [دانلود مستقیم / Download File]({direct_link})\n\n")
                f.write("> کاری از کانال رسمی [@OneForAllHub](https://t.me/OneForAllHub)\n")

if __name__ == "__main__":
    main()
