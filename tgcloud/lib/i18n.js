import { db, sql } from 'sdk/db';
import { users } from '../schema.js';

const langCache = new Map();

export async function getUserLang(userId) {
  const id = Number(userId);
  if (!id) return 'en';
  if (langCache.has(id)) return langCache.get(id);

  try {
    const row = await db.get(sql`SELECT lang FROM users WHERE chat_id = ${id}`);
    if (row && row.lang) {
      langCache.set(id, row.lang);
      return row.lang;
    }
  } catch (_) {
    try {
      await db.run(sql`CREATE TABLE IF NOT EXISTS users (chat_id INTEGER PRIMARY KEY, lang TEXT DEFAULT 'en')`);
    } catch (_) {}
  }

  langCache.set(id, 'en');
  return 'en';
}

export async function setUserLang(userId, lang) {
  const id = Number(userId);
  const target = lang === 'fa' ? 'fa' : 'en';
  langCache.set(id, target);

  try {
    await db.run(sql`CREATE TABLE IF NOT EXISTS users (chat_id INTEGER PRIMARY KEY, lang TEXT DEFAULT 'en')`);
    await db.run(sql`INSERT OR REPLACE INTO users (chat_id, lang) VALUES (${id}, ${target})`);
  } catch (err) {
    console.warn('Set user lang error:', err);
  }
  return target;
}

export const texts = {
  en: {
    startTitle: "👋 <b>Welcome to OneForAllHub Media Downloader!</b>",
    startSubtitle: "All-in-one high-speed serverless downloader for HD videos, Reels, photos, and studio-quality 192kbps MP3 audio — 100% free & unlimited.",
    guideHeading: "💡 <b>3 Ways to Use OneForAllHub:</b>",
    
    way1Title: "1️⃣ <b>Direct in Chat (Fastest):</b>",
    way1Desc: "• Just paste any media link right here in this chat.\n• The bot automatically detects the platform and sends your HD video, original artwork, or tagged MP3 audio.",
    
    way2Title: "2️⃣ <b>Telegram Mini App:</b>",
    way2Desc: "• Tap <b>🚀 Launch Mini App</b> below for a sleek in-app interface with preview, quality selector, and 1-tap downloads.",
    
    way3Title: "3️⃣ <b>Web Browser:</b>",
    way3Desc: "• Tap <b>🌐 Web Browser</b> to use the desktop/mobile web version at full 10Gbps speed without needing Telegram.",
    
    platforms: "📥 <b>Supported Platforms:</b>\n• ▶️ <b>YouTube</b> — 1080p / 720p / 480p / 360p &amp; MP3\n• 📸 <b>Instagram</b> — Reels, Posts, Photos &amp; Stories\n• 🎵 <b>Spotify</b> — 192kbps MP3 + Cover Art &amp; ID3 Tags\n• 🎬 <b>TikTok</b> — Full HD (No Watermark) &amp; Audio\n• 🐦 <b>Twitter / X</b> — Original HD Videos &amp; GIFs\n• 📌 <b>Pinterest</b> — Original 4K Images &amp; Videos\n• ☁️ <b>SoundCloud</b> — High-Quality MP3 Audio\n• 👽 <b>Reddit</b> — HD Videos with Audio\n• 📘 <b>Facebook</b> — Public Videos &amp; Reels\n• 🌐 <b>+ 1,000+ Other Sites</b> — Vimeo, Twitch, Dailymotion, Bluesky, Threads, Tumblr &amp; more!\n",
    channel: "📢 <b>Official Channel:</b> @OneForAllHub",
    
    btnMiniApp: "🚀 Launch Mini App",
    btnWebsite: "🌐 Web Browser",
    btnLang: "🌐 Language / تغییر زبان",
    btnChannel: "📢 Join Channel",
    
    subRequired: "🔒 <b>Channel Membership Required</b>\n\nTo use <b>OneForAllHub Downloader</b> for free with unlimited bandwidth, please join our official channel:\n\n👉 <b>@OneForAllHub</b>\n\nAfter joining, click the <b>Verify & Continue</b> button below to unlock instant downloads!",
    subBtnJoin: "📢 Join @OneForAllHub",
    subBtnVerify: "✅ Verify & Continue",
    subVerified: "✨ <b>Subscription Verified!</b>\n\nYou now have full, high-speed access to <b>OneForAllHub Media Downloader</b>.\nPaste any video, photo, or music link to get started!",
    subNotJoined: "⚠️ You haven't joined @OneForAllHub yet! Please join first.",
    
    invalidUrl: "⚠️ <b>Invalid Link</b>\n\nPlease send a valid link from YouTube, Instagram, Spotify, TikTok, Twitter/X, Pinterest, SoundCloud, Reddit, or Facebook.\n<i>Example:</i> <code>https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b</code>",
    nsfwBlocked: "⛔ <b>Restricted Content (+18)</b>\n\nSorry, due to <b>Telegram's Terms of Service</b> and platform policies, this bot is unable to process or download +18 / pornographic content.",
    invalidYtUrl: "⚠️ <b>Invalid YouTube Link</b>\n\nCould not extract a valid YouTube video ID. Please check the URL and try again.",
    
    ytCaption: "🎬 <b>Select a quality to download directly in chat:</b>",
    igCaption: "📸 <b>Instagram Media Detected!</b>\n\n👇 Choose your desired format to download:",
    genCaption: "🔗 <b>Media Link Detected:</b>\n\n👇 Choose format to proceed with high-speed download:",
    
    tkDownloading: "⏳ <b>Downloading TikTok Video (No Watermark)...</b>",
    twDownloading: "⏳ <b>Downloading Twitter / X HD Media...</b>",
    
    langSelectTitle: "🌐 <b>Select Your Language / زبان خود را انتخاب کنید:</b>",
    langChanged: "✅ <b>Language set to English!</b>"
  },
  
  fa: {
    startTitle: "👋 <b>به ربات دانلودر OneForAllHub خوش آمدید!</b>",
    startSubtitle: "دانلودر همه‌کاره و پرسرعت بدون سرور برای دریافت ویدیوهای HD، ریلز، تصاویر با کیفیت اصلی و موزیک MP3 با کاور و تگ — کاملاً رایگان و نامحدود.",
    guideHeading: "💡 <b>راهنمای ۳ روش استفاده:</b>",
    
    way1Title: "1️⃣ <b>مستقیم در چت ربات (سریع‌ترین روش):</b>",
    way1Desc: "• کافیست لینک هر ویدیو، پست یا موزیک را همینجا در چت بفرستید.\n• ربات به‌صورت خودکار پلتفرم را تشخیص داده و فایل HD یا MP3 را برایتان ارسال می‌کند.",
    
    way2Title: "2️⃣ <b>مینی‌اپ تلگرام (Mini App):</b>",
    way2Desc: "• روی دکمه <b>🚀 اجرای مینی‌اپ</b> کلیک کنید تا اپلیکیشن اختصاصی داخل تلگرام با پیش‌نمایش و انتخاب کیفیت باز شود.",
    
    way3Title: "3️⃣ <b>نسخه وب‌سایت (مرورگر):</b>",
    way3Desc: "• روی دکمه <b>🌐 وب‌سایت</b> کلیک کنید تا در کامپیوتر یا موبایل بدون نیاز به تلگرام با سرعت ۱۰ گیگابیت دانلود کنید.",
    
    platforms: "📥 <b>پلتفرم‌های پشتیبانی‌شده:</b>\n• ▶️ <b>YouTube</b> — ویدیو 1080p / 720p / 480p / 360p و MP3\n• 📸 <b>Instagram</b> — ریلز، پست، عکس و استوری\n• 🎵 <b>Spotify</b> — موزیک 192kbps MP3 با کاور و تگ ID3\n• 🎬 <b>TikTok</b> — کیفیت اصلی (بدون واترمارک) و صوت\n• 🐦 <b>Twitter / X</b> — ویدیوها و گیف‌های HD اصلی\n• 📌 <b>Pinterest</b> — تصاویر ۴K و ویدیوهای اصلی\n• ☁️ <b>SoundCloud</b> — دانلود موزیک MP3 با کیفیت بالا\n• 👽 <b>Reddit</b> — ویدیوهای HD همراه با صدا\n• 📘 <b>Facebook</b> — ویدیوها و ریلزهای عمومی\n• 🌐 <b>و بیش از ۱۰۰۰ سایت دیگر</b> — Vimeo، Twitch، Dailymotion، Bluesky، Threads، Tumblr و...\n",
    channel: "📢 <b>کانال رسمی:</b> @OneForAllHub",
    
    btnMiniApp: "🚀 اجرای مینی‌اپ",
    btnWebsite: "🌐 وب‌سایت",
    btnLang: "🌐 Language / تغییر زبان",
    btnChannel: "📢 عضویت در کانال",
    
    subRequired: "🔒 <b>عضویت در کانال الزامی است</b>\n\nبرای استفاده رایگان و نامحدود از ربات، لطفاً ابتدا در کانال رسمی ما عضو شوید:\n\n👉 <b>@OneForAllHub</b>\n\nپس از عضویت، روی دکمه «تایید عضویت» کلیک کنید تا دانلودها فعال شوند!",
    subBtnJoin: "📢 عضویت در @OneForAllHub",
    subBtnVerify: "✅ تایید عضویت",
    subVerified: "✨ <b>عضویت شما با موفقیت تایید شد!</b>\n\nشما اکنون دسترسی کامل و نامحدود به ربات دارید.\nکافیست لینک ویدیو، عکس یا موزیک دلخواه خود را بفرستید!",
    subNotJoined: "⚠️ شما هنوز در کانال @OneForAllHub عضو نشده‌اید! لطفاً ابتدا عضو شوید.",
    
    invalidUrl: "⚠️ <b>لینک نامعتبر</b>\n\nلطفاً یک لینک معتبر از یوتیوب، اینستاگرام، اسپاتیفای، تیک‌تاک، توییتر/X، پینترست، ساندکلود، ردیت یا فیسبوک ارسال کنید.\n<i>مثال:</i> <code>https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b</code>",
    nsfwBlocked: "⛔ <b>محتوای غیرمجاز (+۱۸)</b>\n\nمتاسفیم؛ به دلیل <b>قوانین تلگرام</b>، این ربات قادر به پردازش و دانلود لینک‌های حاوی محتوای بزرگسالان (+۱۸ / پورن) نیست.",
    invalidYtUrl: "⚠️ <b>لینک نامعتبر یوتیوب</b>\n\nشناسه ویدیو یافت نشد. لطفاً لینک کامل ویدیو را ارسال نمایید.",
    
    ytCaption: "🎬 <b>کیفیت مورد نظر خود را برای دانلود انتخاب کنید:</b>",
    igCaption: "📸 <b>رسانه اینستاگرام شناسایی شد!</b>\n\n👇 فرمت مورد نظر خود را برای دریافت انتخاب کنید:",
    genCaption: "🔗 <b>لینک رسانه شناسایی شد:</b>\n\n👇 فرمت دلخواه را برای دانلود پرسرعت انتخاب کنید:",
    
    tkDownloading: "⏳ <b>در حال دانلود ویدیوی تیک‌تاک (بدون واترمارک)...</b>",
    twDownloading: "⏳ <b>در حال دریافت ویدیوی توییتر / X با کیفیت اصلی...</b>",
    
    langSelectTitle: "🌐 <b>زبان خود را انتخاب کنید / Select Your Language:</b>",
    langChanged: "✅ <b>زبان ربات با موفقیت به فارسی تغییر کرد!</b>"
  }
};

export function buildStartMessage(lang = 'en', miniAppUrl, webPagesUrl, channelUrl) {
  const t = texts[lang] || texts.en;
  const text = [
    t.startTitle,
    '',
    t.startSubtitle,
    '',
    '━━━━━━━━━━━━━━━━━━━',
    t.guideHeading,
    '',
    t.way1Title,
    t.way1Desc,
    '',
    t.way2Title,
    t.way2Desc,
    '',
    t.way3Title,
    t.way3Desc,
    '━━━━━━━━━━━━━━━━━━━',
    '',
    t.platforms,
    t.channel
  ].join('\n');

  const keyboard = {
    inline_keyboard: [
      [
        { text: t.btnMiniApp, web_app: { url: miniAppUrl } },
        { text: t.btnWebsite, url: webPagesUrl }
      ],
      [
        { text: t.btnLang, callback_data: 'choose_lang' },
        { text: t.btnChannel, url: channelUrl }
      ]
    ]
  };

  return { text, reply_markup: keyboard };
}
