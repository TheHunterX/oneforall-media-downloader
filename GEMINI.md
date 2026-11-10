# OneForAllHub Media Downloader — Engineering Rules & Invariants

## 1. Telegram Serverless (tgcloud) V8 Streaming
- **Fetch Timeout:** Outbound `fetch()` in tgcloud V8 isolates has a strict 5-second socket timeout.
- **Range Chunking:** For media files > 10MB up to 50MB, download in 8MB chunks using HTTP `Range: bytes=start-end` headers and assemble them into a single `Uint8Array`.
- **In-Chat Ceiling:** Telegram Bot API limits in-chat file delivery to 50MB. All files <= 50MB MUST be delivered natively as playable video/audio (`supports_streaming: true`).
- **Large Files (>50MB):** Always provide a clear explanation that Telegram restricts in-chat bot delivery over 50MB, and supply the direct CDN link.

## 2. YouTube & Multi-Platform Engine (scripts/download.py)
- **Extractor Args:** Never use `android` or `ios` player clients when authenticated web browser cookies are loaded.
- **Format Cascading:** Support all standard resolutions: 1080p, 720p, 480p, 360p, and MP3.
- **Cascading Fallback Order:**
  1. `yt-dlp` with cookies (clean standard clients)
  2. `yt-dlp` anonymous via 10Gbps Cloudflare WARP proxy
  3. `yt-dlp` with TV/Web client extraction
  4. Single progressive MP4 fallback (`best[ext=mp4]/best`)
- **Direct Edge Engine:** Support direct stream bypass (<2s) for TikTok (No Watermark) and Twitter/X before invoking heavy runners.

## 3. GitHub Actions CI/CD & Notification Safety
- **Fail-Safe Delivery:** Step `Notify & Deliver to Telegram` must always execute using `if: always() && github.event.inputs.chat_id != ''`.
- **Failure Alerts:** If extraction fails, immediately notify the Telegram user with an actionable alert to prevent hanging on loading states.

## 4. UI & UX Standards
- **Progress Tracking:** In both bot and web app, provide visual progress indicators (`[████░░░░] %`) with countdown timers.
- **Self-Contained Bot:** In Telegram, deliver files natively inside the chat without distracting website redirects.
