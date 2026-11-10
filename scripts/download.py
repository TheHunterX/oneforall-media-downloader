import os
import sys
import re
import time
import json
import shutil
import base64
import urllib.request
import urllib.parse
import subprocess
from pathlib import Path
from typing import Optional

def get_ytdlp_cmd() -> list:
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    return [sys.executable, "-m", "yt_dlp"]

def write_state(status: str, percent: int = 0, text: str = "", remaining: int = 0):
    state_file = os.environ.get("DL_STATE_FILE", "/tmp/dl_state.json")
    try:
        data = {"status": status, "percent": percent, "text": text, "remaining": remaining}
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass

def report_progress(percent: int, status_text: str, remaining: int = 0):
    write_state("progress", percent, status_text, remaining)
    log(f"Live Progress state: {percent}% - {status_text}")

def log(msg: str):
    print(f"[OneForAllDownloader] {msg}", flush=True)

def get_cookie_args(for_url: str = "") -> list:
    if for_url and not ("youtube.com" in for_url or "youtu.be" in for_url):
        return []
    for c in [Path("cookies.txt"), Path("/tmp/cookies.txt")]:
        if c.exists() and c.stat().st_size > 50:
            log(f"Found authenticated cookies file for YouTube: {c} ({c.stat().st_size} bytes)")
            return ["--cookies", str(c)]
    return []

def sanitize_url(raw_url: str) -> str:
    """Clean and normalize media URLs, stripping playlists, trackers, and session params."""
    raw_url = raw_url.strip()
    
    # 1. YouTube: Extract pure 11-char video ID and strip playlist/mix parameters
    if "youtube.com" in raw_url or "youtu.be" in raw_url:
        match = re.search(r'(?:v=|/shorts/|/embed/|youtu\.be/|/v/)([a-zA-Z0-9_-]{8,15})', raw_url)
        if match:
            clean_id = match.group(1)
            log(f"Sanitized YouTube URL to pure video: {clean_id}")
            return f"https://www.youtube.com/watch?v={clean_id}"

    # 2. Instagram: Strip ?igsh= and query trackers
    if "instagram.com" in raw_url:
        clean = raw_url.split("?")[0].rstrip("/")
        return clean + "/"

    # 3. TikTok: Strip tracking params
    if "tiktok.com" in raw_url:
        return raw_url.split("?")[0]

    # 4. Twitter / X: Normalize
    if "twitter.com" in raw_url or "x.com" in raw_url:
        return raw_url.split("?")[0]

    return raw_url

def extract_media_id(url: str) -> str:
    """Extract a safe identifier for deterministic file naming."""
    yt_m = re.search(r'(?:v=|/shorts/|/embed/|youtu\.be/|/v/)([a-zA-Z0-9_-]{8,15})', url)
    if yt_m:
        return yt_m.group(1)
    ig_m = re.search(r'(?:reel|p|tv)/([a-zA-Z0-9_-]+)', url)
    if ig_m:
        return ig_m.group(1)
    tk_m = re.search(r'video/([0-9]+)', url)
    if tk_m:
        return tk_m.group(1)
    tw_m = re.search(r'status/([0-9]+)', url)
    if tw_m:
        return tw_m.group(1)
    return "".join(c for c in url.split("/")[-1] if c.isalnum() or c in ("-", "_"))[:20] or "media"

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

def run_ytdlp_with_progress(cmd: list, env: dict, timeout: int = 45, stage_label: str = "Downloading stream") -> tuple[int, str]:
    """Execute yt-dlp while streaming stdout in real time to capture live byte progress and speeds."""
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

    try:
        for line in proc.stdout:
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

            if time.time() - start_time > timeout:
                proc.kill()
                log(f"Process timed out after {timeout}s!")
                break

        proc.wait(timeout=5)
        return proc.returncode, "".join(output_lines)
    except Exception as e:
        try:
            proc.kill()
        except Exception:
            pass
        return -1, "".join(output_lines)

def download_stream_url(direct_url: str, target: Path, headers: Optional[dict] = None) -> bool:
    """Stream download remote media URL into target path using 64KB buffers with live byte progress."""
    try:
        req_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        if headers:
            req_headers.update(headers)
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
# 1. TikTok Engine (TikWM Direct HD - 0 Watermark)
# =====================================================================
def download_tiktok_tikwm(url: str, output_dir: Path, is_audio: bool = False) -> Optional[Path]:
    log("Attempting TikTok download via TikWM API (HD No Watermark)...")
    api_url = f"https://www.tikwm.com/api/?url={urllib.parse.quote(url)}"
    req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("code") == 0 and "data" in data:
            d = data["data"]
            direct_url = d.get("music") if is_audio else (d.get("play") or d.get("wmplay"))
            vid_id = d.get("id") or extract_media_id(url)
            ext = "mp3" if is_audio else "mp4"
            target = output_dir / f"{vid_id}_OneForAllHub.{ext}"

            log(f"Downloading stream: {direct_url[:60]}...")
            if download_stream_url(direct_url, target):
                return target
    except Exception as e:
        log(f"TikWM error: {e}")
    return None

# =====================================================================
# 2. Twitter / X Dedicated Engine (FxTwitter + VxTwitter + Twitsave CDN)
# =====================================================================
def download_twitter(url: str, output_dir: Path, fmt: str, proxy: Optional[str] = None) -> Optional[Path]:
    log("Attempting Twitter / X download via FxTwitter / VxTwitter / Twitsave CDN engine...")
    report_progress(50, "Extracting Twitter / X high-bitrate stream...")
    clean_id = extract_media_id(url)
    is_audio = fmt == "audio-mp3"
    target_ext = "mp3" if is_audio else "mp4"
    final_file = output_dir / f"{clean_id}_OneForAllHub.{target_ext}"

    # Tier 1: FxTwitter & VxTwitter JSON API (< 200ms)
    try:
        fx_url = re.sub(r'https?://(?:www\.)?(?:twitter\.com|x\.com)/', 'https://api.fxtwitter.com/', url)
        req_fx = urllib.request.Request(fx_url, headers={"User-Agent": "OneForAllDownloader/2.0"})
        with urllib.request.urlopen(req_fx, timeout=10) as r_fx:
            fx_data = json.loads(r_fx.read().decode("utf-8"))
        tweet = fx_data.get("tweet") or {}
        media_Obj = tweet.get("media") or {}
        videos = media_Obj.get("videos") or media_Obj.get("all") or []
        if videos:
            v0 = videos[0]
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

    try:
        encoded = urllib.parse.quote(url)
        api_url = f"https://twitsave.com/info?url={encoded}"
        req = urllib.request.Request(api_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
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
            # Sort candidates by resolution (highest first)
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
# 3. Instagram Multi-Tier Fallback Engine
# =====================================================================
def download_instagram(url: str, output_dir: Path, fmt: str, proxy: Optional[str] = None) -> Optional[Path]:
    log("Attempting Instagram download via Multi-Tier Engine...")
    report_progress(50, "Bypassing restrictions & extracting Instagram Reel...")
    clean_id = extract_media_id(url)
    is_audio = fmt == "audio-mp3"
    target_ext = "mp3" if is_audio else "mp4"
    final_file = output_dir / f"{clean_id}_OneForAllHub.{target_ext}"

    cookie_args = get_cookie_args(url)
    env_with_proxy = {**os.environ}
    if proxy:
        env_with_proxy["HTTP_PROXY"] = proxy
        env_with_proxy["HTTPS_PROXY"] = proxy
        env_with_proxy["http_proxy"] = proxy
        env_with_proxy["https_proxy"] = proxy
        env_with_proxy["NO_PROXY"] = "127.0.0.1,localhost"
        env_with_proxy["no_proxy"] = "127.0.0.1,localhost"

    # Tier 1: yt-dlp with iOS App ID (bypasses Web API rate limits)
    log("Instagram Tier 1: yt-dlp with app_id=ios & impersonation...")
    cmd1 = [
        *get_ytdlp_cmd(),
        "--verbose",
        "--no-playlist",
        "--retries", "3",
        "--socket-timeout", "25",
        "--paths", str(output_dir),
        "-o", f"{clean_id}_OneForAllHub.%(ext)s",
        "--extractor-args", "instagram:app_id=ios",
        "--add-header", "User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 330.0.0.0.0"
    ]
    if cookie_args:
        cmd1.extend(cookie_args)
    if is_audio:
        cmd1.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
    else:
        cmd1.extend(["-f", "bv*+ba/b[height<=1080]/b", "--merge-output-format", "mp4"])
    if proxy:
        cmd1.extend(["--proxy", proxy])
    cmd1.append(url)

    try:
        code1, out1 = run_ytdlp_with_progress(cmd1, env_with_proxy, timeout=45, stage_label="Downloading Instagram Reel")
        log(f"Instagram Tier 1 output:\n{out1[-600:]}")
        f = get_latest_file(output_dir, prefer_video=not is_audio)
        if f:
            log(f"Instagram Tier 1 SUCCESS: {f.name} ({f.stat().st_size} bytes)")
            return f
    except Exception as e:
        log(f"Instagram Tier 1 note: {e}")

    # Tier 1b: yt-dlp with GraphQL / default extractor via proxy
    log("Instagram Tier 1b: yt-dlp with GraphQL api extractor...")
    cmd1b = [
        *get_ytdlp_cmd(),
        "--no-playlist",
        "--paths", str(output_dir),
        "-o", f"{clean_id}_OneForAllHub.%(ext)s",
        "--extractor-args", "instagram:api=graphql"
    ]
    if is_audio:
        cmd1b.extend(["-x", "--audio-format", "mp3"])
    else:
        cmd1b.extend(["-f", "bv*+ba/b", "--merge-output-format", "mp4"])
    if proxy:
        cmd1b.extend(["--proxy", proxy])
    cmd1b.append(url)
    try:
        code1b, out1b = run_ytdlp_with_progress(cmd1b, env_with_proxy, timeout=30, stage_label="Downloading Instagram stream")
        log(f"Instagram Tier 1b output:\n{out1b[-400:]}")
        f = get_latest_file(output_dir, prefer_video=not is_audio)
        if f:
            log(f"Instagram Tier 1b SUCCESS: {f.name} ({f.stat().st_size} bytes)")
            return f
    except Exception as e:
        log(f"Instagram Tier 1b note: {e}")

    # Tier 2: OpenGraph Crawler spoofing (ddinstagram / mirrors)
    log("Instagram Tier 2: OpenGraph mirror crawler...")
    shortcode_m = re.search(r'(?:reel|p|tv)/([a-zA-Z0-9_-]+)', url)
    if shortcode_m:
        shortcode = shortcode_m.group(1)
        mirrors = [
            f"https://ddinstagram.com/reel/{shortcode}/",
            f"https://kkinstagram.com/reel/{shortcode}/",
            f"https://instagramez.com/reel/{shortcode}/"
        ]
        for mirror_url in mirrors:
            try:
                log(f"Checking mirror: {mirror_url}...")
                req = urllib.request.Request(mirror_url, headers={
                    "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
                    "Accept-Language": "en-US,en;q=0.9"
                })
                with urllib.request.urlopen(req, timeout=8) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
                    vids = re.findall(r'property=["\']og:video(?::secure_url)?["\']\s+content=["\']([^"\']+)["\']', html)
                    if not vids:
                        vids = re.findall(r'content=["\']([^"\']+)["\']\s+property=["\']og:video(?::secure_url)?["\']', html)
                    if vids:
                        cdn_url = vids[0].replace("&amp;", "&")
                        log(f"Found direct Meta CDN URL: {cdn_url[:70]}...")
                        temp_mp4 = output_dir / f"temp_{clean_id}.mp4" if is_audio else final_file
                        if download_stream_url(cdn_url, temp_mp4):
                            if is_audio:
                                try:
                                    subprocess.run([
                                        "ffmpeg", "-y", "-threads", "0", "-i", str(temp_mp4),
                                        "-vn", "-ar", "44100", "-ac", "2", "-b:a", "192k",
                                        str(final_file)
                                    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                except Exception as fe:
                                    log(f"FFmpeg conversion note: {fe}")
                                try: temp_mp4.unlink()
                                except Exception: pass
                                if final_file.exists() and final_file.stat().st_size > 1000:
                                    return final_file
                            else:
                                return final_file
            except Exception as me:
                log(f"Mirror {mirror_url} note: {me}")

    # Tier 3: General yt-dlp fallback (without cookies if cookies triggered 400 checkpoint)
    log("Instagram Tier 3: yt-dlp anonymous web extraction...")
    return download_general_ytdlp(url, output_dir, fmt, proxy=proxy)

# =====================================================================
# 4. YouTube Engine (High-Speed pytubefix + Authenticated yt-dlp + FFmpeg)
# =====================================================================
def download_youtube(url: str, output_dir: Path, fmt: str, proxy: Optional[str] = None) -> Optional[Path]:
    """
    Rock-solid multi-strategy YouTube engine supporting 1080p, 720p, 480p, 360p and 192k MP3.
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

    # Select height cap
    if fmt == "video-1080p":
        v_filter = "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b"
    elif fmt == "video-720p":
        v_filter = "bv*[height<=720]+ba/b[height<=720]/bv*+ba/b"
    elif fmt == "video-480p":
        v_filter = "bv*[height<=480]+ba/b[height<=480]/bv*+ba/b"
    elif fmt == "video-360p":
        v_filter = "bv*[height<=360]+ba/b[height<=360]/bv*+ba/b"
    elif is_audio:
        v_filter = "ba/b"
    else:
        v_filter = "bv*+ba/b"

    cookie_args = get_cookie_args(url)

    plans = []
    # Primary: If WARP proxy is active, it provides 100% bypass against YouTube datacenter bot detection
    if proxy:
        plans.append(("WARP proxy anonymous mobile/web", [], ["--extractor-args", "youtube:player_client=android,web"], True))
        if cookie_args:
            plans.append(("WARP proxy with cookies", cookie_args, ["--extractor-args", "youtube:player_client=web,mweb"], True))
        plans.append(("WARP proxy TV client", cookie_args if cookie_args else [], ["--extractor-args", "youtube:player_client=tv"], True))
        if not is_audio:
            plans.append(("WARP proxy progressive MP4", [], ["-f", "18/best[ext=mp4]/best"], True))

    # Fallbacks: Native direct connection
    plans.append(("Direct anonymous mobile/web", [], ["--extractor-args", "youtube:player_client=android,web"], False))
    if cookie_args:
        plans.append(("Direct with cookies", cookie_args, ["--extractor-args", "youtube:player_client=web,mweb"], False))
    plans.append(("Direct TV client", cookie_args if cookie_args else [], ["--extractor-args", "youtube:player_client=tv"], False))
    if not is_audio:
        plans.append(("Direct progressive MP4", [], ["-f", "18/best[ext=mp4]/best"], False))

    for plan_name, c_args, extra_args, use_proxy in plans:
        log(f"YouTube Engine trying: {plan_name} (proxy={use_proxy})...")
        cmd = [
            *get_ytdlp_cmd(),
            "--no-playlist",
            "--force-ipv4",
            "--socket-timeout", "20",
            "--retries", "2",
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
            code, out_str = run_ytdlp_with_progress(cmd, plan_env, timeout=45, stage_label="Downloading YouTube stream")
            log(f"Plan output summary: {out_str[-250:]}")
            f = get_latest_file(output_dir, prefer_video=not is_audio)
            if f and f.stat().st_size > 1000:
                log(f"SUCCESS with {plan_name}: {f.name} ({f.stat().st_size} bytes)")
                return f
        except Exception as pe:
            log(f"Plan {plan_name} note: {pe}")

    return None

# =====================================================================
# 4.5. Pinterest Dedicated Engine (High-Resolution Images & Full HD Videos)
# =====================================================================
def download_pinterest(url: str, output_dir: Path, fmt: str, proxy: Optional[str] = None) -> Optional[Path]:
    log("Attempting native Pinterest HD/4K extractor...")
    report_progress(50, "Resolving original Pinterest media asset...")
    clean_id = extract_media_id(url)
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5'
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            final_url = resp.geturl()
            html = resp.read().decode('utf-8', errors='ignore')

        m_id = re.search(r'/pin/([0-9]+)', final_url) or re.search(r'/pin/([0-9]+)', url)
        pin_id = m_id.group(1) if m_id else clean_id

        # 1. Check for Video
        vid_meta = re.search(r'<meta[^>]+(?:property="og:video"|name="twitter:player:stream")[^>]+content="([^"]+)"', html)
        if not vid_meta:
            vid_meta = re.search(r'<meta[^>]+content="([^"]+)"[^>]+(?:property="og:video"|name="twitter:player:stream")', html)
        vid_json = re.search(r'https://v1\.pinimg\.com/videos/[^"\'\s<>\)]+\.mp4', html)
        video_url = vid_meta.group(1) if vid_meta else (vid_json.group(0) if vid_json else None)

        if video_url:
            log(f"Found Pinterest video: {video_url}")
            dest = output_dir / f"{pin_id}_OneForAllHub.mp4"
            v_req = urllib.request.Request(video_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(v_req, timeout=30) as v_resp, open(dest, 'wb') as f:
                f.write(v_resp.read())
            if dest.exists() and dest.stat().st_size > 1000:
                log(f"Successfully downloaded Pinterest video: {dest.name} ({dest.stat().st_size} bytes)")
                return dest

        # 2. Check for Image
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
            if preload_m:
                raw_img = preload_m.group(1).replace(r'\/', '/')
                img_url = re.sub(r'/(?:736x|564x|474x|236x|1200x)/', '/originals/', raw_img)

        if img_url:
            log(f"Found Pinterest image: {img_url}")
            ext = 'png' if '.png' in img_url.lower() else ('webp' if '.webp' in img_url.lower() else 'jpg')
            dest = output_dir / f"{pin_id}_OneForAllHub.{ext}"

            try:
                i_req = urllib.request.Request(img_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(i_req, timeout=20) as i_resp, open(dest, 'wb') as f:
                    f.write(i_resp.read())
            except urllib.error.HTTPError as e:
                if e.code in (403, 404):
                    alt_url = re.sub(r'\.jpg$', '.png', img_url) if ext == 'jpg' else re.sub(r'\.png$', '.jpg', img_url)
                    alt_ext = 'png' if ext == 'jpg' else 'jpg'
                    dest = output_dir / f"{pin_id}_OneForAllHub.{alt_ext}"
                    i_req = urllib.request.Request(alt_url, headers={'User-Agent': 'Mozilla/5.0'})
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
            "--retries", "5",
            "--socket-timeout", "25",
            "--paths", str(output_dir),
            "-o", f"{clean_id}_OneForAllHub.%(ext)s"
        ]
        if use_cookies and cookie_args:
            c.extend(cookie_args)
        if is_audio:
            c.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
        elif fmt == "video-1080p":
            c.extend(["-f", "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b", "--merge-output-format", "mp4"])
        elif fmt == "video-720p":
            c.extend(["-f", "bv*[height<=720]+ba/b[height<=720]/bv*+ba/b", "--merge-output-format", "mp4"])
        else:
            c.extend(["-f", "bv*+ba/b", "--merge-output-format", "mp4"])
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
            code, out_str = run_ytdlp_with_progress(cmd, env_with_proxy, timeout=90, stage_label="Downloading media stream")
            log("yt-dlp output summary:\n" + out_str[-600:])
            f = get_latest_file(output_dir, prefer_video=not is_audio)
            if f:
                return f
        except subprocess.TimeoutExpired:
            log("General yt-dlp timed out after 90 seconds.")
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
    is_audio = fmt == "audio-mp3"

    url = sanitize_url(raw_url)
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

    # Step 1: TikTok High-Speed Direct Engine
    if "tiktok.com" in url:
        target_file = download_tiktok_tikwm(url, output_dir, is_audio=is_audio)

    # Step 2: Twitter / X Dedicated Engine
    if (not target_file or not target_file.exists()) and ("twitter.com" in url or "x.com" in url):
        target_file = download_twitter(url, output_dir, fmt, proxy=warp_proxy)

    # Step 3: Instagram Dedicated Engine
    if (not target_file or not target_file.exists()) and ("instagram.com" in url):
        target_file = download_instagram(url, output_dir, fmt, proxy=warp_proxy)

    # Step 4: YouTube Multi-Tier Engine
    if (not target_file or not target_file.exists()) and ("youtube.com" in url or "youtu.be" in url):
        target_file = download_youtube(url, output_dir, fmt, proxy=warp_proxy)

    # Step 4.5: Pinterest Dedicated Engine (Images & Videos)
    if (not target_file or not target_file.exists()) and ("pinterest.com" in url or "pin.it" in url):
        target_file = download_pinterest(url, output_dir, fmt, proxy=warp_proxy)

    # Step 5: General yt-dlp Engine (Pinterest, SoundCloud, Reddit, Vimeo, etc.)
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

    if target_file.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
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
    meta = {
        "filename": target_file.name,
        "filesize": target_file.stat().st_size,
        "duration": duration_sec,
        "width": width,
        "height": height,
        "actual_res": actual_res,
        "thumb_b64": thumb_b64
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
