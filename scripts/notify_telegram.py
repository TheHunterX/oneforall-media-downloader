import os
import sys
import re
import time
import json
import urllib.request
import urllib.parse
from pathlib import Path

def clean_media_filename(name: str, is_audio: bool = False) -> str:
    """Normalize media filename, stripping DASH stream suffixes and double extensions."""
    name = name.strip()
    # Strip double extensions
    name = re.sub(r'\.(mp4|mkv|webm|mov)\.mp3$', '.mp3', name, flags=re.IGNORECASE)
    name = re.sub(r'\.(mp3|m4a|aac)\.mp4$', '.mp4', name, flags=re.IGNORECASE)
    # Strip yt-dlp DASH format artifacts like .fdash-1924932338667157v
    name = re.sub(r'\.f(?:dash-[a-zA-Z0-9_-]+|[0-9]+)(?=\.[a-zA-Z0-9]+$)', '', name)
    return name

def notify_user():
    if len(sys.argv) < 7:
        print("Usage: notify_telegram.py <filename> <filesize> <direct_url> <url> <format> <chat_id> [actual_res] [status] [message_id]")
        return

    raw_filename = sys.argv[1].strip()
    filesize_str = sys.argv[2].strip()
    direct_url = sys.argv[3].strip()
    raw_url = sys.argv[4].strip()
    req_fmt = sys.argv[5].strip()
    chat_id_str = sys.argv[6].strip()
    actual_res = sys.argv[7].strip() if len(sys.argv) > 7 else ""
    job_status = sys.argv[8].strip() if len(sys.argv) > 8 else "success"
    message_id_str = sys.argv[9].strip() if len(sys.argv) > 9 else ""
    duration_str = sys.argv[10].strip() if len(sys.argv) > 10 else "0"
    width_str = sys.argv[11].strip() if len(sys.argv) > 11 else "0"
    height_str = sys.argv[12].strip() if len(sys.argv) > 12 else "0"

    msg_id = int(message_id_str) if message_id_str.isdigit() else 0
    duration = int(duration_str) if duration_str.isdigit() else 0
    width = int(width_str) if width_str.isdigit() else 0
    height = int(height_str) if height_str.isdigit() else 0

    filename = clean_media_filename(raw_filename, "audio" in req_fmt)

    # Load shared metadata if available from download.py
    thumb_b64 = ""
    try:
        meta_p = Path("/tmp/media_meta.json")
        if meta_p.exists():
            with open(meta_p, "r", encoding="utf-8") as mf:
                mdata = json.load(mf)
                if not duration and mdata.get("duration"):
                    duration = int(mdata["duration"])
                if not width and mdata.get("width"):
                    width = int(mdata["width"])
                if not height and mdata.get("height"):
                    height = int(mdata["height"])
                if not actual_res and mdata.get("actual_res"):
                    actual_res = mdata["actual_res"]
                thumb_b64 = mdata.get("thumb_b64", "")
        if not thumb_b64 and Path("/tmp/thumb_b64.txt").exists():
            thumb_b64 = Path("/tmp/thumb_b64.txt").read_text(encoding="utf-8").strip()
    except Exception as me:
        print(f"[Notify] Shared metadata read note: {me}")

    if not chat_id_str:
        print("[Notify] Missing chat_id. Skipping notification.")
        return

    token = os.environ.get("TGCLOUD_TOKEN", "").strip()
    if not token:
        print("[Notify] TGCLOUD_TOKEN environment secret is not set. Skipping.")
        return

    app_id = token.split(":")[0] if ":" in token else "app9005060404"

    # Handle Failure Case
    if job_status == "failure" or not direct_url:
        print(f"[Notify] Processing failed for chat {chat_id_str}. Sending error notice...")
        fail_js = r"""
import { api } from 'sdk';

export default async function(args) {
    const NL = String.fromCharCode(10);
    if (args.message_id) {
        try {
            await api.deleteMessage({
                chat_id: args.chat_id,
                message_id: args.message_id
            });
        } catch (_) {}
    }
    try {
        const failText = [
            '❌ <b>Download Failed</b>',
            '',
            'We could not process this video stream. The media may be private, age-restricted, or temporarily unavailable.',
            '',
            'Please check the link or choose another quality format.',
            '',
            '📡 @OneForAllHub'
        ].join(NL);

        await api.sendMessage({
            chat_id: args.chat_id,
            parse_mode: 'HTML',
            text: failText
        });
    } catch (e) {
        console.error('Failed to send failure alert:', e);
    }
    return { ok: true };
}
"""
        payload = {
            "module": "endpoints/notify_failure",
            "sources": {"endpoints/notify_failure": fail_js},
            "args": {
                "chat_id": int(chat_id_str),
                "message_id": msg_id
            }
        }
        try:
            req = urllib.request.Request(
                f"https://cloud.telegram.org/{app_id}/manage/run",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                print(f"[Notify] Failure notice sent to {chat_id_str}: {resp.read().decode('utf-8')}")
        except Exception as fe:
            print(f"[Notify] Could not send failure alert: {fe}")
        return

    # Verify and pre-resolve direct_url to fast blob storage URL before invoking tgcloud V8
    resolved_url = direct_url
    print(f"[Notify] Verifying CDN edge availability for {filename}...")
    for attempt in range(15):
        try:
            req = urllib.request.Request(direct_url, method="HEAD", headers={"User-Agent": "OneForAllNotifier"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status in (200, 302):
                    resolved_url = resp.geturl()
                    print(f"[Notify] CDN edge verified live (status {resp.status}) at attempt {attempt+1}")
                    break
        except urllib.error.HTTPError as he:
            if he.code in (301, 302, 307, 308):
                resolved_url = he.headers.get("Location") or direct_url
                print(f"[Notify] CDN redirect resolved (HTTP {he.code}) at attempt {attempt+1}")
                break
            print(f"[Notify] Waiting for CDN edge propagation (HTTP {he.code})... ({attempt+1}/15)")
        except Exception as ex:
            print(f"[Notify] Waiting for CDN edge propagation... ({attempt+1}/15): {ex}")
        time.sleep(1.5)

    size_bytes = int(filesize_str) if filesize_str.isdigit() else 0
    size_mb = f"{size_bytes / (1024 * 1024):.1f}"

    filename_low = filename.lower()
    is_video_file = filename_low.endswith((".mp4", ".mkv", ".mov", ".webm"))
    is_audio_file = filename_low.endswith((".mp3", ".m4a", ".aac", ".ogg", ".wav"))
    is_image_file = filename_low.endswith((".jpg", ".jpeg", ".png", ".webp"))

    if is_image_file:
        fmt_name = f"Original Image ({filename.split('.')[-1].upper()})"
    elif is_audio_file or ("audio" in req_fmt and not is_video_file):
        fmt_name = "Audio MP3 (Original 192kbps)"
    elif actual_res:
        fmt_name = f"Video {actual_res}"
    elif "1080" in req_fmt:
        fmt_name = "Video 1080p (Full HD)"
    elif "480" in req_fmt:
        fmt_name = "Video 480p (Medium)"
    elif "360" in req_fmt:
        fmt_name = "Video 360p (Low)"
    else:
        fmt_name = "Video 720p (HD)"

    # JS Code for tgcloud V8 isolate supporting up to 50MB via HTTP Range chunking (respecting 30MB per-fetch cap)
    js_code = r"""
import { api, fetch, InputFile } from 'sdk';

async function fetchSingleRange(url, rangeHeader) {
    const headers = { 'User-Agent': 'OneForAllBot' };
    if (rangeHeader) headers['Range'] = rangeHeader;
    const res = await fetch(url, { headers });
    if (!res.ok && res.status !== 206) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    const chunks = [];
    let total = 0;
    for await (const c of res.body) {
        chunks.push(c);
        total += c.length;
    }
    const buf = new Uint8Array(total);
    let off = 0;
    for (const c of chunks) {
        buf.set(c, off);
        off += c.length;
    }
    return buf;
}

async function fetchMediaBytes(url, totalSize) {
    const MAX_SINGLE = 25 * 1024 * 1024; // 25MB per request (safely below 30MB V8 fetch cap)
    if (!totalSize || totalSize <= MAX_SINGLE) {
        return await fetchSingleRange(url, null);
    }
    const ranges = [];
    for (let start = 0; start < totalSize; start += MAX_SINGLE) {
        const end = Math.min(start + MAX_SINGLE - 1, totalSize - 1);
        ranges.push({ start, end });
    }
    const parts = await Promise.all(ranges.map(async ({ start, end }) => {
        const buf = await fetchSingleRange(url, `bytes=${start}-${end}`);
        return { start, buf };
    }));
    const totalLen = parts.reduce((acc, p) => acc + p.buf.length, 0);
    const assembled = new Uint8Array(Math.max(totalSize, totalLen));
    for (const p of parts) {
        assembled.set(p.buf, p.start);
    }
    return assembled.subarray(0, totalLen);
}

function parseMp4Duration(data) {
    try {
        const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
        const limit = Math.min(data.length - 32, 256 * 1024);
        for (let i = 0; i < limit; i++) {
            if (data[i] === 0x6D && data[i+1] === 0x76 && data[i+2] === 0x68 && data[i+3] === 0x64) {
                const ver = data[i + 4];
                if (ver === 0) {
                    const ts = view.getUint32(i + 16);
                    const dur = view.getUint32(i + 20);
                    if (ts > 0) return Math.round(dur / ts);
                } else if (ver === 1) {
                    const ts = view.getUint32(i + 24);
                    const dur = (view.getUint32(i + 28) * 0x100000000) + view.getUint32(i + 32);
                    if (ts > 0) return Math.round(dur / ts);
                }
            }
        }
    } catch (_) {}
    return 0;
}

function parseMp3Duration(data) {
    try {
        let offset = 0;
        if (data.length > 10 && data[0] === 0x49 && data[1] === 0x44 && data[2] === 0x33) {
            const tagSize = ((data[6] & 0x7f) << 21) | ((data[7] & 0x7f) << 14) | ((data[8] & 0x7f) << 7) | (data[9] & 0x7f);
            offset = 10 + tagSize;
        }
        const audioBytes = Math.max(0, data.length - offset);
        return Math.max(1, Math.round((audioBytes * 8) / 192000));
    } catch (_) {
        return 0;
    }
}

export default async function(args) {
    const NL = String.fromCharCode(10);
    const rawFilename = (args.filename || 'media');
    const cleanFilename = rawFilename
        .replace(/\.(mp4|mkv|webm|mov)\.mp3$/i, '.mp3')
        .replace(/\.(mp3|m4a|aac)\.mp4$/i, '.mp4')
        .replace(/\.f(?:dash-[a-zA-Z0-9_-]+|[0-9]+)(?=\.[a-zA-Z0-9]+$)/i, '');
    const filenameLow = cleanFilename.toLowerCase();
    const isExplicitVideoExt = filenameLow.endsWith('.mp4') || filenameLow.endsWith('.mkv') || filenameLow.endsWith('.mov') || filenameLow.endsWith('.webm');
    const isExplicitAudioExt = filenameLow.endsWith('.mp3') || filenameLow.endsWith('.m4a') || filenameLow.endsWith('.aac') || filenameLow.endsWith('.flac') || filenameLow.endsWith('.wav');
    const isExplicitImageExt = filenameLow.endsWith('.jpg') || filenameLow.endsWith('.jpeg') || filenameLow.endsWith('.png') || filenameLow.endsWith('.webp');

    const isAudio = !isExplicitVideoExt && !isExplicitImageExt && (isExplicitAudioExt || (args.req_fmt && args.req_fmt.includes('audio')));
    const isImage = isExplicitImageExt;
    const totalSize = args.size_bytes || 0;
    const MAX_TELEGRAM_BOT_BYTES = 50 * 1024 * 1024;

    const caption = [
        '✅ <b>Your Media is Ready!</b>',
        '',
        '📁 <b>File:</b> <code>' + cleanFilename + '</code>',
        '🎯 <b>Quality:</b> <b>' + (args.fmt_name || 'HD') + '</b>',
        '📦 <b>Size:</b> <b>' + args.size_mb + ' MB</b>',
        '',
        '📡 @OneForAllHub'
    ].join(NL);

    const keyboard = {
        inline_keyboard: [
            [{ text: '📥 Direct Download File (High-Speed CDN)', url: args.direct_url }]
        ]
    };

    function decodeB64(b64) {
        if (!b64) return null;
        try {
            const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
            let str = b64.replace(/=+$/, '');
            let len = str.length;
            let bytes = new Uint8Array(Math.floor(len * 3 / 4));
            let bi = 0;
            for (let i = 0; i < len; i += 4) {
                let n = (chars.indexOf(str[i]) << 18) |
                        (chars.indexOf(str[i+1]) << 12) |
                        ((i+2 < len ? chars.indexOf(str[i+2]) : 0) << 6) |
                        (i+3 < len ? chars.indexOf(str[i+3]) : 0);
                bytes[bi++] = (n >> 16) & 0xff;
                if (i+2 < len) bytes[bi++] = (n >> 8) & 0xff;
                if (i+3 < len) bytes[bi++] = n & 0xff;
            }
            return bytes.subarray(0, bi);
        } catch (_) {
            return null;
        }
    }

    let delivered = false;

    if (totalSize > 0 && totalSize <= MAX_TELEGRAM_BOT_BYTES) {
        try {
            const streamUrl = args.resolved_url || args.direct_url;
            let loc = streamUrl;
            try {
                if (streamUrl.includes('github.com/')) {
                    const ghRes = await fetch(streamUrl, { redirect: 'manual', headers: { 'User-Agent': 'OneForAllBot' } });
                    loc = (ghRes && ghRes.headers && ghRes.headers.get('location')) || streamUrl;
                }
            } catch (_) {}

            const allBytes = await fetchMediaBytes(loc, totalSize);
            const dur = (args.duration && args.duration > 0)
                ? args.duration
                : (isAudio ? parseMp3Duration(allBytes) : parseMp4Duration(allBytes));

            if (isImage) {
                const sendPhotoParams = {
                    chat_id: args.chat_id,
                    photo: new InputFile(allBytes, cleanFilename),
                    caption: caption,
                    parse_mode: 'HTML',
                    reply_markup: keyboard
                };
                await api.sendPhoto(sendPhotoParams);
                delivered = true;
            } else if (isAudio) {
                const sendAudioParams = {
                    chat_id: args.chat_id,
                    audio: new InputFile(allBytes, cleanFilename),
                    caption: caption,
                    parse_mode: 'HTML',
                    performer: '@OneForAllHub',
                    title: cleanFilename.replace(/_OneForAllHub\..*$/, ''),
                    reply_markup: keyboard
                };
                if (dur > 0) sendAudioParams.duration = dur;
                if (args.thumb_b64) {
                    const tBytes = decodeB64(args.thumb_b64);
                    if (tBytes) sendAudioParams.thumbnail = new InputFile(tBytes, 'thumb.jpg');
                }
                await api.sendAudio(sendAudioParams);
                delivered = true;
            } else {
                const sendVideoParams = {
                    chat_id: args.chat_id,
                    video: new InputFile(allBytes, cleanFilename),
                    caption: caption,
                    parse_mode: 'HTML',
                    supports_streaming: true,
                    reply_markup: keyboard
                };
                if (dur > 0) sendVideoParams.duration = dur;
                if (args.width && args.width > 0) sendVideoParams.width = args.width;
                if (args.height && args.height > 0) sendVideoParams.height = args.height;
                if (args.thumb_b64) {
                    const tBytes = decodeB64(args.thumb_b64);
                    if (tBytes) sendVideoParams.thumbnail = new InputFile(tBytes, 'thumb.jpg');
                }
                await api.sendVideo(sendVideoParams);
                delivered = true;
            }
        } catch (streamErr) {
            console.warn('Native delivery error, falling back to message:', streamErr.message);
        }
    }

    if (!delivered) {
        const largeCaption = [
            '⚠️ <b>Telegram In-Chat File Limit Exceeded (>50MB)</b>',
            '',
            '📁 <b>File:</b> <code>' + cleanFilename + '</code>',
            '🎯 <b>Quality:</b> <b>' + (args.fmt_name || 'HD') + '</b>',
            '📦 <b>Size:</b> <b>' + args.size_mb + ' MB</b>',
            '',
            '⚡ <b>Notice:</b> Telegram bot API restricts bots from sending files larger than 50MB directly in chat.',
            '🚀 <b>Instant Download:</b> Click the high-speed CDN button below to download or stream full-quality directly.',
            '',
            '📡 @OneForAllHub'
        ].join(NL);

        await api.sendMessage({
            chat_id: args.chat_id,
            parse_mode: 'HTML',
            text: (totalSize > MAX_TELEGRAM_BOT_BYTES) ? largeCaption : caption,
            reply_markup: keyboard
        });
    }

    if (args.message_id) {
        try {
            await api.deleteMessage({
                chat_id: args.chat_id,
                message_id: args.message_id
            });
        } catch (delErr) {
            try {
                await api.editMessageCaption({
                    chat_id: args.chat_id,
                    message_id: args.message_id,
                    parse_mode: 'HTML',
                    caption: '✅ <b>100% Complete | Delivered below</b>' + NL + NL + '📡 @OneForAllHub'
                });
            } catch (_) {
                try {
                    await api.editMessageText({
                        chat_id: args.chat_id,
                        message_id: args.message_id,
                        parse_mode: 'HTML',
                        text: '✅ <b>100% Complete | Delivered below</b>' + NL + NL + '📡 @OneForAllHub'
                    });
                } catch (_) {}
            }
        }
    }

    return { ok: true, delivered: delivered };
}
"""

    payload = {
        "module": "endpoints/deliver_media",
        "sources": {
            "endpoints/deliver_media": js_code
        },
        "args": {
            "chat_id": int(chat_id_str),
            "filename": filename,
            "fmt_name": fmt_name,
            "size_mb": size_mb,
            "size_bytes": size_bytes,
            "req_fmt": req_fmt,
            "direct_url": direct_url,
            "resolved_url": resolved_url,
            "message_id": msg_id,
            "duration": duration,
            "width": width,
            "height": height,
            "thumb_b64": thumb_b64
        }
    }

    req = urllib.request.Request(
        f"https://cloud.telegram.org/{app_id}/manage/run",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"[Notify] Delivery SUCCESS to chat {chat_id_str}: {data}")
    except Exception as e:
        print(f"[Notify] Delivery request error: {e}")

if __name__ == "__main__":
    notify_user()
