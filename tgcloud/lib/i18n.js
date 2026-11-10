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
    startSubtitle: "High-speed serverless downloader for YouTube, Instagram, TikTok, and Twitter / X with original HD quality.",
    guideHeading: "💡 <b>3 Ways to Use This Bot:</b>",
    
    way1Title: "1️⃣ <b>Direct in Chat (No App Needed):</b>",
    way1Desc: "• Simply send any media link (YouTube, Instagram, TikTok, Twitter/X, Pinterest) directly in this chat.\n• The bot will immediately process and deliver your HD video, 4K original artwork, or MP3 audio file.",
    
    way2Title: "2️⃣ <b>Telegram Mini App:</b>",
    way2Desc: "• Tap the <b>🚀 Launch Mini App</b> button below.\n• Enjoy an interactive app experience inside Telegram with video player, quality selector, and 1-click downloads.",
    
    way3Title: "3️⃣ <b>Web Browser:</b>",
    way3Desc: "• Tap the <b>🌐 Web Browser</b> button to open the web version on desktop or mobile.\n• Fast 10Gbps downloads without needing Telegram.",
    
    platforms: "📥 <b>Supported:</b> YouTube (1080p/720p/MP3) • Instagram • TikTok (No Watermark) • Twitter/X • Pinterest",
    channel: "📢 <b>Official Channel:</b> @OneForAllHub",
    
    btnMiniApp: "🚀 Launch Mini App",
    btnWebsite: "🌐 Web Browser",
    btnLang: "🌐 Language / تغییر زبان",
    btnChannel: "📢 Join Channel",
    
    subRequired: "🔒 <b>Channel Membership Required</b>\n\nTo use <b>OneForAllHub Downloader</b> for free with unlimited bandwidth, please join our official channel:\n\n👉 <b>@OneForAllHub</b>\n\nAfter joining, click the <b>Verify & Continue</b> button below to unlock instant downloads!",
    subBtnJoin: "📢 Join @OneForAllHub",
    subBtnVerify: "✅ Verify & Continue",
    subVerified: "✨ <b>Subscription Verified!</b>\n\nYou now have full, high-speed access to <b>OneForAllHub Media Downloader</b>.\nPaste any video or audio link to get started!",
    subNotJoined: "⚠️ You haven't joined @OneForAllHub yet! Please join first.",
    
    invalidUrl: "⚠️ <b>Invalid Link</b>\n\nPlease send a valid media link from YouTube, TikTok, Twitter/X, Instagram, or Pinterest.\n<i>Example:</i> <code>https://x.com/NASA/status/1732824684683784516</code>",
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
    startSubtitle: "سریع‌ترین ربات دانلود مدیا از یوتیوب، اینستاگرام، تیک‌تاک و توییتر / X با کیفیت اصلی و بدون قطعی.",
    guideHeading: "💡 <b>راهنمای ۳ روش استفاده:</b>",
    
    way1Title: "1️⃣ <b>بدون برنامه (مستقیم در چت ربات):</b>",
    way1Desc: "• کافیست هر لینکی (یوتیوب، اینستاگرام، تیک‌تاک، توییتر، پینترست) را همینجا در چت بفرستید.\n• ربات بلافاصله فایل ویدیویی، تصویر با کیفیت اصلی ۴K یا صوت MP3 را برایتان ارسال می‌کند.",
    
    way2Title: "2️⃣ <b>مینی‌اپ تلگرام (Mini App داخل تلگرام):</b>",
    way2Desc: "• روی دکمه <b>🚀 اجرای مینی‌اپ</b> کلیک کنید تا محیط اپلیکیشن داخل تلگرام باز شود.\n• امکان تماشای آنلاین، پیش‌نمایش و انتخاب کیفیت ویدیو یا MP3 را با ۱ کلیک خواهید داشت.",
    
    way3Title: "3️⃣ <b>نسخه وب‌سایت (مرورگر):</b>",
    way3Desc: "• روی دکمه <b>🌐 وب‌سایت</b> کلیک کنید تا در کامپیوتر یا مرورگر از سایت پرسرعت استفاده کنید.\n• دانلود مستقیم فایل‌ها با نهایت پهنای باند ۱۰ گیگابیت بدون نیاز به تلگرام.",
    
    platforms: "📥 <b>پلتفرم‌ها:</b> YouTube (1080p/720p/MP3) • Instagram • TikTok • Twitter/X • Pinterest",
    channel: "📢 <b>کانال رسمی:</b> @OneForAllHub",
    
    btnMiniApp: "🚀 اجرای مینی‌اپ",
    btnWebsite: "🌐 وب‌سایت",
    btnLang: "🌐 Language / تغییر زبان",
    btnChannel: "📢 عضویت در کانال",
    
    subRequired: "🔒 <b>عضویت در کانال الزامی است</b>\n\nبرای استفاده رایگان و نامحدود از ربات، لطفاً ابتدا در کانال رسمی ما عضو شوید:\n\n👉 <b>@OneForAllHub</b>\n\nپس از عضویت، روی دکمه «تایید عضویت» کلیک کنید تا دانلودها فعال شوند!",
    subBtnJoin: "📢 عضویت در @OneForAllHub",
    subBtnVerify: "✅ تایید عضویت",
    subVerified: "✨ <b>عضویت شما با موفقیت تایید شد!</b>\n\nشما اکنون دسترسی کامل و نامحدود به ربات دارید.\nکافیست لینک ویدیوی دلخواه خود را بفرستید!",
    subNotJoined: "⚠️ شما هنوز در کانال @OneForAllHub عضو نشده‌اید! لطفاً ابتدا عضو شوید.",
    
    invalidUrl: "⚠️ <b>لینک نامعتبر</b>\n\nلطفاً یک آدرس معتبر از یوتیوب، تیک‌تاک، توییتر، اینستاگرام یا پینترست ارسال کنید.\n<i>مثال:</i> <code>https://x.com/NASA/status/1732824684683784516</code>",
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
