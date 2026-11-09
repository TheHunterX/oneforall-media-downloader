import os
import sys
import re
import json
import urllib.request
import urllib.parse
import subprocess
from pathlib import Path
from typing import Optional

def log(msg: str):
    print(f"[OneForAllDownloader] {msg}", flush=True)

def sanitize_url(raw_url: str) -> str:
    """Clean and normalize media URLs, stripping playlists, trackers, and session params."""
    raw_url = raw_url.strip()
    
    # 1. YouTube: Extract pure 11-char video ID and strip playlist/mix parameters
    if "youtube.com" in raw_url or "youtu.be" in raw_url:
        match = re.search(r'(?:v=|youtu\.be/|shorts/|embed/)([a-zA-Z0-9_-]{11})', raw_url)
        if match:
            clean_id = match.group(1)
            log(f"Sanitized YouTube URL from playlist/mix to pure video: {clean_id}")
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

def check_warp_proxy() -> Optional[str]:
    """Check if the local Cloudflare WARP proxy (wireproxy) is running on port 8080 or 1080."""
    candidates = ["http://127.0.0.1:8080", "socks5://127.0.0.1:1080"]
    for proxy_url in candidates:
        try:
            req = urllib.request.Request("https://www.cloudflare.com/cdn-cgi/trace", headers={"User-Agent": "curl/7.68.0"})
            proxy_support = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
            opener = urllib.request.build_opener(proxy_support)
            with opener.open(req, timeout=3) as resp:
                data = resp.read().decode('utf-8')
                if "warp=on" in data or "ip=" in data:
                    log(f"Verified active WARP proxy tunnel on {proxy_url}!")
                    return proxy_url
        except Exception:
            pass
    return None

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
            title = d.get("title", "tiktok_video")[:60]
            safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip() or "tiktok"
            ext = "mp3" if is_audio else "mp4"
            target = output_dir / f"{safe_title}.{ext}"

            log(f"Downloading stream: {direct_url[:60]}...")
            stream_req = urllib.request.Request(direct_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(stream_req, timeout=30) as s_resp, open(target, "wb") as f:
                while chunk := s_resp.read(64 * 1024):
                    f.write(chunk)
            if target.exists() and target.stat().st_size > 0:
                log(f"TikWM SUCCESS: Saved {target.name} ({target.stat().st_size} bytes)")
                return target
    except Exception as e:
        log(f"TikWM error: {e}")
    return None

def get_latest_file(output_dir: Path, min_size: int = 1000) -> Optional[Path]:
    files = list(output_dir.glob("*"))
    valid = [f for f in files if f.is_file() and not f.name.endswith(".part") and not f.name.endswith(".ytdl") and f.stat().st_size > min_size]
    if valid:
        valid.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return valid[0]
    return None

def download_youtube_ytdlp(url: str, output_dir: Path, fmt: str, proxy: Optional[str] = None) -> Optional[Path]:
    is_audio = fmt == "audio-mp3"
    
    # Common format arguments
    if is_audio:
        fmt_args = ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
    elif fmt == "video-1080p":
        fmt_args = ["-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/bestvideo+bestaudio/best", "--merge-output-format", "mp4"]
    elif fmt == "video-720p":
        fmt_args = ["-f", "bestvideo[height<=720]+bestaudio/best[height<=720]/bestvideo+bestaudio/best", "--merge-output-format", "mp4"]
    else:
        fmt_args = ["-f", "bestvideo+bestaudio/best", "--merge-output-format", "mp4"]

    base_cmd = [
        "yt-dlp",
        "--verbose",
        "--no-playlist",
        "--retries", "5",
        "--socket-timeout", "20",
        "--paths", str(output_dir),
        "-o", "%(title).80s [%(id)s].%(ext)s"
    ]

    # Environment with proxy and strict NO_PROXY to protect localhost:4416
    env_with_proxy = {**os.environ}
    if proxy:
        env_with_proxy["HTTP_PROXY"] = proxy
        env_with_proxy["HTTPS_PROXY"] = proxy
        env_with_proxy["http_proxy"] = proxy
        env_with_proxy["https_proxy"] = proxy
        env_with_proxy["NO_PROXY"] = "127.0.0.1,localhost"
        env_with_proxy["no_proxy"] = "127.0.0.1,localhost"

    # --- Strategy 1: pytubefix high-speed WARP client (Proven 100% Reliable for YouTube) ---
    log("YouTube Strategy 1: Attempting high-speed pytubefix with WARP proxy...")
    try:
        from pytubefix import YouTube
        proxies = {"http": proxy, "https": proxy} if proxy else None
        for client in ("MWEB", "WEB", "TV", "TV_EMBED", "ANDROID_VR"):
            try:
                log(f"Trying pytubefix client: {client}...")
                yt = YouTube(url, client=client, proxies=proxies)
                title = yt.title or "youtube_media"
                safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip() or "video"
                safe_ascii = "".join(c for c in title if c.isascii() and (c.isalnum() or c in ("-", "_"))).strip()
                suffix = "OneForAllHub" if not safe_ascii else ""
                ext = "mp3" if is_audio else "mp4"
                filename = f"{safe_title[:50]}_{suffix}.{ext}".replace("__", "_").strip("_")

                if is_audio:
                    stream = yt.streams.get_audio_only()
                else:
                    stream = yt.streams.get_highest_resolution()

                if stream:
                    path = stream.download(output_path=str(output_dir), filename=filename)
                    tf = Path(path)
                    if tf.exists() and tf.stat().st_size > 1000:
                        log(f"Strategy 1 SUCCESS ({client}): {tf.name} ({tf.stat().st_size} bytes)")
                        return tf
            except Exception as client_err:
                log(f"pytubefix {client} failed: {client_err}")
    except Exception as e:
        log(f"pytubefix error: {e}")

    # --- Strategy 2: WARP proxy env + BgUtil PO-Token Provider ---
    log("YouTube Strategy 2: Attempting yt-dlp with BgUtil PO-Token + WARP env...")
    cmd2 = base_cmd + fmt_args + [
        "--extractor-args", "youtubepot-bgutilhttp:base_url=http://127.0.0.1:4416",
        "--extractor-args", "youtube:player-client=mweb,tv,web_safari,web",
        url
    ]
    try:
        res2 = subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env_with_proxy, timeout=30)
        log(f"Strategy 2 exit code: {res2.returncode}\n{res2.stdout[-1000:]}")
        f = get_latest_file(output_dir)
        if f:
            log(f"Strategy 2 SUCCESS: {f.name} ({f.stat().st_size} bytes)")
            return f
    except subprocess.TimeoutExpired:
        log("Strategy 2 timed out after 30 seconds. Moving to next strategy.")

    # --- Strategy 3: WARP proxy env + TV & VR player clients ---
    log("YouTube Strategy 3: Attempting TV / VR clients with WARP env...")
    cmd3 = base_cmd + fmt_args + [
        "--extractor-args", "youtube:player-client=tv,android_vr,tv_embedded",
        url
    ]
    try:
        res3 = subprocess.run(cmd3, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env_with_proxy, timeout=30)
        log(f"Strategy 3 exit code: {res3.returncode}\n{res3.stdout[-1000:]}")
        f = get_latest_file(output_dir)
        if f:
            log(f"Strategy 3 SUCCESS: {f.name} ({f.stat().st_size} bytes)")
            return f
    except subprocess.TimeoutExpired:
        log("Strategy 3 timed out after 30 seconds. Moving to next strategy.")

    # --- Strategy 4: Standard yt-dlp directly with CLI --proxy flag ---
    if proxy:
        log("YouTube Strategy 4: Attempting standard yt-dlp with CLI --proxy flag...")
        cmd4 = base_cmd + ["--proxy", proxy] + fmt_args + [
            "--extractor-args", "youtube:player-client=tv,mweb,web",
            url
        ]
        try:
            res4 = subprocess.run(cmd4, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
            log(f"Strategy 4 exit code: {res4.returncode}\n{res4.stdout[-1000:]}")
            f = get_latest_file(output_dir)
            if f:
                log(f"Strategy 4 SUCCESS: {f.name} ({f.stat().st_size} bytes)")
                return f
        except subprocess.TimeoutExpired:
            log("Strategy 4 timed out after 30 seconds.")

    return None

def download_general_ytdlp(url: str, output_dir: Path, fmt: str, proxy: Optional[str] = None) -> Optional[Path]:
    log(f"Attempting general yt-dlp download (format={fmt})...")
    is_audio = fmt == "audio-mp3"
    
    cmd = [
        "yt-dlp",
        "--verbose",
        "--no-playlist",
        "--retries", "5",
        "--socket-timeout", "25",
        "--paths", str(output_dir),
        "-o", "%(title).80s [%(id)s].%(ext)s"
    ]

    env_with_proxy = {**os.environ}
    if proxy:
        env_with_proxy["HTTP_PROXY"] = proxy
        env_with_proxy["HTTPS_PROXY"] = proxy
        env_with_proxy["http_proxy"] = proxy
        env_with_proxy["https_proxy"] = proxy
        env_with_proxy["NO_PROXY"] = "127.0.0.1,localhost"
        env_with_proxy["no_proxy"] = "127.0.0.1,localhost"

    if is_audio:
        cmd.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
    elif fmt == "video-1080p":
        cmd.extend(["-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/bestvideo+bestaudio/best", "--merge-output-format", "mp4"])
    elif fmt == "video-720p":
        cmd.extend(["-f", "bestvideo[height<=720]+bestaudio/best[height<=720]/bestvideo+bestaudio/best", "--merge-output-format", "mp4"])
    else:
        cmd.extend(["-f", "bestvideo+bestaudio/best", "--merge-output-format", "mp4"])

    cmd.append(url)
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env_with_proxy, timeout=120)
        log("yt-dlp output summary:\n" + res.stdout[-1000:])
        f = get_latest_file(output_dir)
        if f:
            return f
    except subprocess.TimeoutExpired:
        log("General yt-dlp timed out after 120 seconds.")
    return get_latest_file(output_dir)

def upload_media_cdn(file_path: Path) -> Optional[str]:
    log(f"Uploading {file_path.name} ({file_path.stat().st_size} bytes) to high-speed CDN...")
    
    # 1. Try tmpfiles.org (Instant direct download link, up to 10GB)
    try:
        log("Trying tmpfiles.org upload...")
        cmd = ["curl", "-s", "-F", f"file=@{file_path}", "https://tmpfiles.org/api/v1/upload"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
        data = json.loads(res.stdout)
        if data.get("status") == "success" and "data" in data and "url" in data["data"]:
            raw_url = data["data"]["url"]
            # Convert https://tmpfiles.org/123/name.mp4 -> https://tmpfiles.org/dl/123/name.mp4
            direct_url = raw_url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
            log(f"tmpfiles.org direct link: {direct_url}")
            return direct_url
    except Exception as e:
        log(f"tmpfiles.org error: {e}")

    # 2. Try uguu.se (Instant direct download, up to 100MB)
    try:
        log("Trying uguu.se upload...")
        cmd = ["curl", "-s", "-F", f"files[]=@{file_path}", "https://uguu.se/upload.php"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
        data = json.loads(res.stdout)
        if data.get("success") and "files" in data and len(data["files"]) > 0:
            link = data["files"][0].get("url")
            if link:
                log(f"uguu.se direct link: {link}")
                return link
    except Exception as e:
        log(f"uguu.se error: {e}")

    # 3. Try Pixeldrain (if API key is available)
    api_key = os.environ.get("PIXELDRAIN_API_KEY")
    try:
        log("Trying Pixeldrain upload...")
        cmd = ["curl", "-s", "-F", f"file=@{file_path}"]
        if api_key:
            cmd.extend(["-u", f":{api_key}"])
        cmd.append("https://pixeldrain.com/api/file")
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
        data = json.loads(res.stdout)
        file_id = data.get("id")
        if file_id:
            link = f"https://pixeldrain.com/api/file/{file_id}?download"
            log(f"Pixeldrain direct link: {link}")
            return link
    except Exception as e:
        log(f"Pixeldrain error: {e}")

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
    # Clear out any leftover files
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

    # Step 2: YouTube Multi-Tier Engine (WARP Proxy, PO-Token, BgUtil, TV Client, pytubefix)
    if (not target_file or not target_file.exists()) and ("youtube.com" in url or "youtu.be" in url):
        target_file = download_youtube_ytdlp(url, output_dir, fmt, proxy=warp_proxy)

    # Step 3: General yt-dlp Engine (Instagram, Twitter, Pinterest, SoundCloud, etc.)
    if not target_file or not target_file.exists() or target_file.stat().st_size == 0:
        target_file = download_general_ytdlp(url, output_dir, fmt, proxy=warp_proxy)

    if not target_file or not target_file.exists() or target_file.stat().st_size < 1000:
        log("ERROR: All download engines failed to retrieve this media link.")
        sys.exit(1)

    log(f"SUCCESS: Downloaded file {target_file.name} ({target_file.stat().st_size} bytes)")

    # Output variables for GitHub Actions
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"filename={target_file.name}\n")
            f.write(f"filesize={target_file.stat().st_size}\n")
            f.write(f"filepath={target_file.resolve()}\n")

    # Upload to CDN for direct link
    direct_link = upload_media_cdn(target_file)
    if direct_link:
        if github_output:
            with open(github_output, "a", encoding="utf-8") as f:
                f.write(f"direct_url={direct_link}\n")

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
