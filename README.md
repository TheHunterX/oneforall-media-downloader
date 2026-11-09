# 🚀 OneForAllHub Media Downloader (Serverless Suite)

[🇮🇷 راهنمای فارسی](#راهنمای-فارسی) | [🇬🇧 English Guide](#english-guide)

---

<a name="راهنمای-فارسی"></a>
## 🇮🇷 راهنمای فارسی

پروژه دانلودر چندمنظوره و **کاملاً بدون نیاز به سرور (Serverless)** برای دانلود ویدیو، ریلز و موزیک از **یوتیوب، اینستاگرام، تیک‌تاک، توییتر و پینترست** بدون یک ریال هزینه سرور یا VPS.

طراحی و بهینه‌سازی شده برای اعضای کانال **[OneForAllHub](https://t.me/OneForAllHub)**.

---

### 🌟 ساختار سه‌گانه پروژه و وضعیت فعال‌سازی

#### ۱. ربات تلگرام رسمی روی کلود سرورلس تلگرام (Telegram Serverless / tgcloud) 🤖 ✅
- پروژه مستقیماً با **Telegram Serverless (`@tgcloud/cli`)** و توکن رسمی شما متصل و روی ایزوله‌های ابری V8 تلگرام مستقر (Deploy) شده است.
- نیازی به سرور خارجی یا وب‌هوک دستی ندارد؛ کدها در پوشه `tgcloud/` قرار دارند و به محض ارسال لینک توسط کاربر در تلگرام، ویدیو یا فایل صوتی را تحویل می‌دهند.
- فرآیند انتشار مجدد خودکار با ورک‌فلو `.github/workflows/deploy-tgcloud.yml` تنظیم شده است.

#### ۲. وب‌اپلیکیشن تحت وب (GitHub Pages) 🌐 ✅
- یک سایت زیبا، واکنش‌گرا و دوزبانه (فارسی و انگلیسی) با قابلیت سوییچ در لحظه (`fa` / `en`).
- دانلود بدون واترمارک ویدیوهای TikTok (با کیفیت HD).
- استخراج مستقیم موزیک و صوت MP3 از ویدیوها همراه با پیش‌نمایش.
- اجرا روی شبکه توزیع محتوای رایگان GitHub Pages.
- 🔗 **آدرس وب‌اپلیکیشن:** [thehunterx.github.io/oneforall-media-downloader](https://thehunterx.github.io/oneforall-media-downloader/)

#### ۳. رانر دانلود ابری در اکشنز گیت‌هاب (GitHub Actions yt-dlp) ⚡ ✅
- دانلود ویدیوهای سنگین و با کیفیت بالا (4K / 1080p / 60fps) از یوتیوب و تیک‌تاک با سرعت ۱۰ گیگابیت بر ثانیه رانرهای اوبونتو گیت‌هاب.
- تست‌شده در عمل و با موفقیت برای دانلود فایل تصویری MP4 و استخراج فایل صوتی MP3.
- آپلود لینک مستقیم و پرسرعت CDN و همچنین ذخیره فایل در بخش Artifacts گیت‌هاب یا ارسال مستقیم به تلگرام.

---

<a name="english-guide"></a>
## 🇬🇧 English Guide

A multi-platform, **100% Serverless Media Downloader Suite** to download videos, reels, and audio from **YouTube, Instagram, TikTok (No Watermark), Twitter / X, and Pinterest** with zero VPS maintenance.

Optimized for **[OneForAllHub](https://t.me/OneForAllHub)**.

### 🌟 Project Components & Live Status

#### 1. Native Telegram Serverless Bot (`tgcloud`) 🤖 ✅
- Deployed on **Telegram's native Serverless infrastructure** using `@tgcloud/cli` inside V8 engine isolates.
- Automated CI/CD deployment configured in `.github/workflows/deploy-tgcloud.yml`.
- Handles incoming messages directly from Telegram users and responds with HD media files.

#### 2. Serverless Web App (GitHub Pages) 🌐 ✅
- Responsive Dark Mode UI with instantaneous language switching (`fa` / `en`).
- **TikTok:** HD watermark-free video and audio download via TikWM.
- **Instagram & YouTube:** Media and MP3 audio extraction with integrated previews.
- 🔗 **Live Web App:** [thehunterx.github.io/oneforall-media-downloader](https://thehunterx.github.io/oneforall-media-downloader/)

#### 3. Cloud Downloader Runner (GitHub Actions yt-dlp) ⚡ ✅
- Powered by `yt-dlp` with browser impersonation (`curl_cffi`) and Node.js challenge solving.
- Fully tested and verified with real downloads (both MP4 video and MP3 audio).
- Uploads direct high-speed download links (Pixeldrain) and GitHub Artifacts.

---

## 📢 Channels & Contact

- **Telegram Channel:** [@OneForAllHub](https://t.me/OneForAllHub)
