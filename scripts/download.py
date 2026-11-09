import os
import sys
import json
import urllib.request
import urllib.parse
import subprocess
from pathlib import Path

def log(msg: str):
    print(f"[OneForAllDownloader] {msg}", flush=True)

def download_tiktok_tikwm(url: str, output_dir: Path, is_audio: bool = False) -> Path | None:
    log("Attempting TikTok download via TikWM API (No Watermark)...")
    api_url = f"https://www.tikwm.com/api/?url={urllib.parse.quote(url)}"
    req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("code") == 0 and "data" in data:
            d = data["data"]
            direct_url = d.get("music") if is_audio else (d.get("play") or d.get("wmplay"))
            title = d.get("title", "tiktok_video")[:60]
            # Clean filename
            safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip() or "tiktok"
            ext = "mp3" if is_audio else "mp4"
            target = output_dir / f"{safe_title}.{ext}"

            log(f"Downloading stream: {direct_url[:60]}...")
            stream_req = urllib.request.Request(direct_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(stream_req, timeout=30) as s_resp, open(target, "wb") as f:
                while chunk := s_resp.read(64 * 1024):
                    f.write(chunk)
            log(f"Saved: {target.name} ({target.stat().st_size} bytes)")
            return target
    except Exception as e:
        log(f"TikWM error: {e}")
    return None

def download_ytdlp(url: str, output_dir: Path, fmt: str) -> Path | None:
    log(f"Attempting download via yt-dlp (format={fmt})...")
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--retries", "3",
        "--socket-timeout", "30",
        "--js-runtimes", "node",
        "--paths", str(output_dir),
        "-o", "%(title).80s [%(id)s].%(ext)s"
    ]

    # Try impersonation if available
    cmd.extend(["--impersonate", "chrome"])

    if fmt == "audio-mp3":
        cmd.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
    elif fmt == "video-1080p":
        cmd.extend(["-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best", "--merge-output-format", "mp4"])
    elif fmt == "video-720p":
        cmd.extend(["-f", "bestvideo[height<=720]+bestaudio/best[height<=720]/best", "--merge-output-format", "mp4"])
    else:
        cmd.extend(["-f", "bestvideo+bestaudio/best", "--merge-output-format", "mp4"])

    # Additional client fallbacks for YouTube
    if "youtube.com" in url or "youtu.be" in url:
        cmd.extend(["--extractor-args", "youtube:player_client=ios,tv_embedded,android"])

    cmd.append(url)
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    log("yt-dlp output:\n" + res.stdout[-1000:])
    
    files = list(output_dir.glob("*"))
    files = [f for f in files if f.is_file() and not f.name.endswith(".part") and not f.name.endswith(".ytdl")]
    if files:
        # Return newest or largest file
        files.sort(key=lambda x: x.stat().st_size, reverse=True)
        return files[0]
    return None

def upload_pixeldrain(file_path: Path) -> str | None:
    log(f"Uploading {file_path.name} to Pixeldrain...")
    try:
        cmd = ["curl", "-s", "-F", f"file=@{file_path}", "https://pixeldrain.com/api/file"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        data = json.loads(res.stdout)
        file_id = data.get("id")
        if file_id:
            return f"https://pixeldrain.com/api/file/{file_id}?download"
    except Exception as e:
        log(f"Upload error: {e}")
    return None

def main():
    if len(sys.argv) < 2:
        print("Usage: python download.py <url> [format]")
        sys.exit(1)

    url = sys.argv[1].strip()
    fmt = sys.argv[2].strip() if len(sys.argv) > 2 else "video-720p"
    is_audio = fmt == "audio-mp3"

    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)

    target_file = None

    # Step 1: Specific high-speed handlers
    if "tiktok.com" in url:
        target_file = download_tiktok_tikwm(url, output_dir, is_audio=is_audio)

    # Step 2: yt-dlp fallback
    if not target_file or not target_file.exists() or target_file.stat().st_size == 0:
        target_file = download_ytdlp(url, output_dir, fmt)

    if not target_file or not target_file.exists() or target_file.stat().st_size == 0:
        log("ERROR: All download methods failed for this URL.")
        sys.exit(1)

    log(f"SUCCESS: Downloaded {target_file.name} ({target_file.stat().st_size} bytes)")

    # Output variables for GitHub Actions
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"filename={target_file.name}\n")
            f.write(f"filesize={target_file.stat().st_size}\n")
            f.write(f"filepath={target_file.resolve()}\n")

    # Upload to Pixeldrain
    direct_link = upload_pixeldrain(target_file)
    if direct_link:
        log(f"Direct download link: {direct_link}")
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
                f.write("> کاری از کانال [@OneForAllHub](https://t.me/OneForAllHub)\n")

if __name__ == "__main__":
    main()
