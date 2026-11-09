# 🚀 OneForAllHub Media Downloader (Serverless)

[🇮🇷 فارسی](#راهنمای-فارسی) | [🇬🇧 English](#english-guide)

---

<a name="راهنمای-فارسی"></a>
## 🇮🇷 راهنمای فارسی

پروژه دانلودر چندمنظوره و **کاملاً بدون نیاز به سرور (Serverless)** برای دانلود ویدیو، ریلز و موزیک از **یوتیوب، اینستاگرام، تیک‌تاک، توییتر و پینترست** بدون یک ریال هزینه سرور یا VPS.

طراحی و بهینه‌سازی شده برای اعضای کانال **[OneForAllHub](https://t.me/OneForAllHub)**.

### 🌟 ساختار سه‌گانه پروژه

#### ۱. وب‌اپلیکیشن تحت وب (GitHub Pages) 🌐
- یک سایت زیبا، واکنش‌گرا و دوزبانه (فارسی و انگلیسی) با قابلیت سوییچ در لحظه.
- دانلود بدون واترمارک ویدیوهای TikTok (با کیفیت HD).
- استخراج مستقیم موزیک و صوت MP3 از ویدیوها.
- بدون نیاز به سرور شخصی (اجرا مستقیم روی CDN رایگان گیت‌هاب پیجز).
- 🔗 **آدرس وب‌اپلیکیشن:** [thehunterx.github.io/oneforall-media-downloader](https://thehunterx.github.io/oneforall-media-downloader/)

#### ۲. رانر دانلود ابری در اکشنز گیت‌هاب (GitHub Actions yt-dlp) ⚡
- دانلود ویدیوهای با کیفیت بالا (4K / 1080p / 60fps) از یوتیوب و هر سایت دیگر با سرعت ۱۰ گیگابیت بر ثانیه رانرهای اوبونتو گیت‌هاب.
- ایجاد لینک مستقیم و پرسرعت دانلود بدون فیلتر در چند ثانیه.
- ارسال خودکار فایل نهایی به کانال یا بات تلگرام شما (در صورت تمایل).

#### ۳. ربات تلگرام بدون سرور روی کلاودفلر (Cloudflare Workers Bot) 🤖
- ربات تلگرام اختصاصی دوزبانه که ۱۰۰٪ روی شبکه سرورلس Cloudflare اجرا می‌شود (تا ۱۰۰ هزار درخواست رایگان در روز!).
- با ارسال هر لینک اینستاگرام، تیک‌تاک یا یوتیوب، بلافاصله ویدیو را در تلگرام تحویل می‌دهد.

---

### 🛠️ نحوه استفاده از دانلودر GitHub Actions

1. در ریپازیتوری وارد تب **Actions** شوید.
2. از لیست سمت چپ روی **Cloud Media Downloader (yt-dlp)** بزنید.
3. دکمه **Run workflow** را بزنید:
   - لینک ویدیو را در کادر قرار دهید.
   - فرمت (Best / 1080p / 720p / MP3) را انتخاب کنید.
   - دکمه **Run workflow** را فشار دهید.
4. بعد از چند ثانیه، لینک مستقیم دانلود در خلاصه اجرای اکشن نمایش داده شده و فایل در بخش Artifacts قابل دانلود است.

---

<a name="english-guide"></a>
## 🇬🇧 English Guide

A multi-platform, **100% Serverless Media Downloader** designed to fetch videos, reels, and audio from **YouTube, Instagram, TikTok (No Watermark), Twitter / X, and Pinterest** with zero server costs or VPS maintenance.

Optimized for **[OneForAllHub](https://t.me/OneForAllHub)** community members.

### 🌟 Project Architecture

#### 1. Serverless Web App (GitHub Pages) 🌐
- Responsive, modern Dark Mode UI with an instant language switch (`fa` / `en`).
- **TikTok:** HD watermark-free video download via TikWM.
- **Instagram & YouTube:** Video and audio extraction with audio preview player.
- 100% hosted on free GitHub Pages CDN.
- 🔗 **Live Web App:** [thehunterx.github.io/oneforall-media-downloader](https://thehunterx.github.io/oneforall-media-downloader/)

#### 2. Cloud Downloader Runner (GitHub Actions yt-dlp) ⚡
- Downloads 4K / 1080p / 60fps heavy media with 10 Gbps gigabit network bandwidth on GitHub's Ubuntu runners.
- Powered by `yt-dlp` with browser impersonation (`curl_cffi`) and Node.js challenge solving.
- Uploads direct high-speed download links (Pixeldrain) and GitHub Artifacts.
- Optional Telegram bot delivery.

#### 3. Zero-Server Telegram Bot (Cloudflare Workers) 🤖
- Runs on free Cloudflare edge workers (100,000 requests/day free tier).
- Bilingual replies in both Persian and English.
- Instant webhook deployment located in `telegram-bot/`.

---

### 🚀 How to Run the Cloud Downloader (GitHub Actions)

1. Navigate to the **Actions** tab in this repository.
2. Select **Cloud Media Downloader (yt-dlp)** from the sidebar.
3. Click **Run workflow**:
   - Paste the video or reel URL.
   - Select the desired format (`video-720p`, `video-1080p`, `audio-mp3`, `video-best`).
   - Click **Run workflow**.
4. Once completed, your direct download link is printed in the summary and the video file is available in the **Artifacts** section.

---

## 📢 Channels & Contact

- **Telegram Channel:** [@OneForAllHub](https://t.me/OneForAllHub)
