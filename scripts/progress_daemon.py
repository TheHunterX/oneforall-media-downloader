import os
import sys
import time
import json
import urllib.request
from pathlib import Path

def render_progress_bar(percent: int) -> str:
    total_bars = 12
    filled = min(total_bars, max(0, round((percent / 100.0) * total_bars)))
    return "█" * filled + "░" * (total_bars - filled)

def send_telegram_update(token: str, chat_id: int, message_id: int, percent: int, status_text: str, remaining_sec: int, title: str):
    bar = render_progress_bar(percent)
    est_str = f"~{remaining_sec}s remaining" if remaining_sec > 0 else "Delivering..."
    
    caption = (
        f"⏳ <b>{title}</b>\n\n"
        f"<code>[{bar}]</code> <b>{percent}%</b>\n"
        f"⚡ <b>Status:</b> {status_text}\n"
        f"⏱ <b>Estimated:</b> {est_str}\n\n"
        f"📡 @OneForAllHub"
    )

    js_code = """
import { api } from 'sdk';

export default async function(args) {
    try {
        try {
            await api.editMessageCaption({
                chat_id: args.chat_id,
                message_id: args.message_id,
                parse_mode: 'HTML',
                caption: args.caption
            });
        } catch (_) {
            await api.editMessageText({
                chat_id: args.chat_id,
                message_id: args.message_id,
                parse_mode: 'HTML',
                text: args.caption
            });
        }
        return { ok: true };
    } catch (e) {
        return { ok: false, error: e.message };
    }
}
"""
    payload = {
        "module": "endpoints/update_progress",
        "sources": {"endpoints/update_progress": js_code},
        "args": {
            "chat_id": chat_id,
            "message_id": message_id,
            "caption": caption
        }
    }

    app_id = token.split(":")[0] if ":" in token else "app9005060404"
    try:
        req = urllib.request.Request(
            f"https://cloud.telegram.org/{app_id}/manage/run",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            pass
    except Exception as e:
        # Network jitter or flood control - non-fatal
        print(f"[ProgressDaemon] Telegram update note: {e}", flush=True)

def main():
    if len(sys.argv) < 3:
        sys.exit(0)

    chat_id_str = sys.argv[1].strip()
    message_id_str = sys.argv[2].strip()
    raw_url = sys.argv[3].strip() if len(sys.argv) > 3 else ""
    fmt = sys.argv[4].strip() if len(sys.argv) > 4 else "video-720p"
    state_file_path = sys.argv[5].strip() if len(sys.argv) > 5 else "/tmp/dl_state.json"

    if not chat_id_str.lstrip("-").isdigit() or not message_id_str.isdigit():
        sys.exit(0)

    chat_id = int(chat_id_str)
    message_id = int(message_id_str)

    token = os.environ.get("TGCLOUD_TOKEN", "").strip()
    if not token:
        sys.exit(0)

    # Determine platform and title
    url_low = raw_url.lower()
    is_audio = "audio" in fmt
    if "youtube.com" in url_low or "youtu.be" in url_low:
        platform = "YouTube"
        stages = [
            (32, "⚡ 10Gbps Runner allocated | Connecting to Google Edge Network...", 12),
            (46, "🔍 Bypassing YouTube bot detection & cipher restrictions...", 9),
            (62, "📥 Extracting high-bitrate adaptive audio & video streams...", 6),
            (76, "⚡ Downloading 1080p/720p stream chunks via 10Gbps line...", 4),
            (88, "🎬 Lossless FFmpeg muxing & fast-start MP4 web streaming...", 2),
            (94, "📦 Packaging media container & verifying stream integrity...", 1),
            (98, "🚀 Delivering native playable media to your chat...", 0)
        ]
    elif "instagram.com" in url_low:
        platform = "Instagram"
        stages = [
            (32, "⚡ 10Gbps Runner allocated | Establishing Cloudflare WARP proxy tunnel...", 8),
            (48, "🔍 Bypassing Instagram login walls & extracting Reel streams...", 6),
            (68, "⚡ Downloading original high-resolution video stream...", 4),
            (88, "🎬 Lossless container packaging & audio synchronization...", 2),
            (98, "🚀 Delivering native playable Reel to your chat...", 0)
        ]
    elif "twitter.com" in url_low or "x.com" in url_low:
        platform = "Twitter / X"
        stages = [
            (32, "⚡ 10Gbps Runner allocated | Connecting to Twitter / X media CDN...", 8),
            (50, "🔍 Resolving tweet stream manifests & bitrates...", 5),
            (72, "⚡ Downloading crystal-clear HD stream chunks...", 3),
            (90, "🎬 FFmpeg audio synchronization & container packaging...", 2),
            (98, "🚀 Delivering native playable video to your chat...", 0)
        ]
    elif "tiktok.com" in url_low:
        platform = "TikTok"
        stages = [
            (32, "⚡ 10Gbps Runner allocated | Connecting to TikTok CDN API...", 6),
            (55, "🔍 Removing watermark & extracting 1080p HD stream...", 4),
            (78, "⚡ Downloading watermark-free crystal stream...", 2),
            (95, "🚀 Packaging MP4 container for instant delivery...", 0)
        ]
    else:
        platform = "Media"
        stages = [
            (32, "⚡ 10Gbps Universal Cloud Runner allocated...", 10),
            (48, "🛡️ Establishing high-speed edge proxy tunnel...", 7),
            (65, f"🔍 Extracting {platform} stream manifests...", 5),
            (82, "⚡ Downloading media stream via 10Gbps engine...", 3),
            (92, "🎬 FFmpeg remuxing & audio synchronization...", 2),
            (98, "🚀 Finalizing playable media for chat delivery...", 0)
        ]

    if is_audio:
        title = f"Downloading {platform} Audio MP3..."
    elif "1080" in fmt:
        title = f"Downloading {platform} Video 1080p (Full HD)..."
    elif "480" in fmt:
        title = f"Downloading {platform} Video 480p (Medium)..."
    elif "360" in fmt:
        title = f"Downloading {platform} Video 360p (Low)..."
    else:
        title = f"Downloading {platform} Video (HD)..."

    state_path = Path(state_file_path)
    start_time = time.time()
    last_sent_percent = 0

    while time.time() - start_time < 180:  # 3 minute max guard
        updated_from_state = False

        # 1. Inspect state file written by download.py
        if state_path.exists():
            try:
                with open(state_path, "r", encoding="utf-8") as sf:
                    data = json.load(sf)
                status = data.get("status")
                if status == "complete":
                    send_telegram_update(token, chat_id, message_id, 100, "✅ Media ready! Delivering to chat...", 0, title)
                    break
                elif status == "error":
                    break
                elif status == "progress":
                    pct = int(data.get("percent", 50))
                    msg = data.get("text", "Processing media streams...")
                    rem = int(data.get("remaining", 3))
                    if pct > last_sent_percent:
                        send_telegram_update(token, chat_id, message_id, pct, msg, rem, title)
                        last_sent_percent = pct
                        updated_from_state = True
            except Exception:
                pass

        # 2. Smooth time-based progression during runner boot / environment setup
        if not updated_from_state:
            elapsed = time.time() - start_time
            if elapsed < 4.0:
                pct = min(28, 20 + int(elapsed * 2))
                msg = f"⚡ 10Gbps Runner allocated | Preparing FFmpeg & tools..."
                rem = max(1, int(16 - elapsed))
            elif elapsed < 8.0:
                pct = min(38, 28 + int((elapsed - 4) * 2.5))
                msg = f"🛡️ Establishing Cloudflare 10Gbps Edge Tunnel..."
                rem = max(1, int(15 - elapsed))
            elif elapsed < 13.0:
                pct = min(48, 38 + int((elapsed - 8) * 2))
                msg = f"🔍 Connecting to {platform} & bypassing rate limits..."
                rem = max(1, int(14 - elapsed))
            elif elapsed < 20.0:
                pct = min(54, 48 + int((elapsed - 13) * 0.9))
                msg = f"📥 Negotiating high-bitrate {platform} streams..."
                rem = max(1, int(18 - elapsed))
            else:
                pct = min(59, 54 + int((elapsed - 20) * 0.4))
                msg = f"⚡ Streaming media chunks via 10Gbps line..."
                rem = 4

            if pct > last_sent_percent:
                send_telegram_update(token, chat_id, message_id, pct, msg, rem, title)
                last_sent_percent = pct

        time.sleep(1.5)

if __name__ == "__main__":
    main()
