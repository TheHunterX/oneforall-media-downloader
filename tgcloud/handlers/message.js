import { api } from 'sdk';
import { db } from 'sdk/db';
import { downloads } from '../schema.js';

function escapeHtml(text) {
  if (!text) return '';
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function sanitizeUrl(rawUrl) {
  if (!rawUrl) return rawUrl;
  const trimmed = rawUrl.trim();

  // 1. YouTube: Extract pure 11-char video ID and strip playlist/mix parameters
  if (trimmed.includes('youtube.com') || trimmed.includes('youtu.be')) {
    const m = trimmed.match(/(?:v=|youtu\.be\/|shorts\/|embed\/)([a-zA-Z0-9_-]{11})/);
    if (m && m[1]) {
      return `https://www.youtube.com/watch?v=${m[1]}`;
    }
  }

  // 2. Instagram: Strip ?igsh= and trackers
  if (trimmed.includes('instagram.com')) {
    return trimmed.split('?')[0].replace(/\/+$/, '') + '/';
  }

  // 3. TikTok: Strip query parameters
  if (trimmed.includes('tiktok.com')) {
    return trimmed.split('?')[0];
  }

  // 4. Twitter / X: Normalize
  if (trimmed.includes('twitter.com') || trimmed.includes('x.com')) {
    return trimmed.split('?')[0];
  }

  return trimmed;
}

async function recordDownload(chatId, url, platform) {
  try {
    if (db && downloads) {
      await db.insert(downloads).values({
        chatId: Number(chatId),
        url: String(url),
        platform: String(platform),
        createdAt: new Date().toISOString()
      });
    }
  } catch (err) {
    console.error('[DB Log Error]', err);
  }
}

export default async function (message) {
  if (!message || !message.text) return;

  const chatId = message.chat.id;
  const text = message.text.trim();

  // If /start or /help command
  if (text.startsWith('/start') || text.startsWith('/help')) {
    await api.sendMessage({
      chat_id: chatId,
      parse_mode: 'HTML',
      text: 
        `👋 <b>سلام! به ربات دانلودر OneForAllHub خوش آمدید.</b>\n` +
        `<i>Welcome to OneForAllHub Serverless Media Downloader.</i>\n\n` +
        `📥 <b>لینک ویدیو یا ریلز خود را ارسال کنید:</b>\n` +
        `<i>Send any video or reel link from:</i>\n\n` +
        `• <b>TikTok</b> (کیفیت اصلی بدون واترمارک / HD No Watermark)\n` +
        `• <b>Instagram</b> (ریلز و پست / Reels & Posts)\n` +
        `• <b>YouTube</b> (کلیپ و موزیک / Clips & Audio)\n` +
        `• <b>Twitter / X & Pinterest</b>\n\n` +
        `⚡ <i>اجرا شده به صورت ۱۰۰٪ Serverless روی کلود تلگرام</i>\n` +
        `📡 <b>کانال رسمی ما / Official Channel:</b> @OneForAllHub`
    });
    return;
  }

  // Extract URL from user input
  const match = text.match(/(https?:\/\/[^\s]+)/);
  if (!match) {
    await api.sendMessage({
      chat_id: chatId,
      text: '⚠️ لطفاً یک لینک معتبر از تیک‌تاک، اینستاگرام، یوتیوب یا توییتر ارسال کنید.\n\nPlease send a valid video URL.'
    });
    return;
  }

  const mediaUrl = sanitizeUrl(match[1]);
  let waitMsg = null;
  try {
    waitMsg = await api.sendMessage({
      chat_id: chatId,
      text: '⏳ در حال دریافت و آماده‌سازی فایل... لطفاً چند لحظه صبر کنید.\nProcessing and extracting media...'
    });
  } catch (_) {}

  // 1. Process TikTok via TikWM API (HD, No Watermark)
  if (mediaUrl.includes('tiktok.com')) {
    try {
      const res = await fetch(`https://www.tikwm.com/api/?url=${encodeURIComponent(mediaUrl)}`, {
        headers: { 'User-Agent': 'Mozilla/5.0' }
      });
      const data = await res.json();
      if (data && data.code === 0 && data.data) {
        const videoUrl = data.data.play || data.data.wmplay;
        const caption = `🎬 <b>${escapeHtml(data.data.title || 'TikTok Video')}</b>\n\n👤 @${data.data.author?.unique_id || 'TikTok'}\n✨ <i>No Watermark HD</i>\n\n📡 @OneForAllHub`;
        
        await api.sendVideo({
          chat_id: chatId,
          video: videoUrl,
          caption: caption,
          parse_mode: 'HTML'
        });

        await recordDownload(chatId, mediaUrl, 'tiktok');

        if (waitMsg && waitMsg.message_id) {
          try { await api.deleteMessage({ chat_id: chatId, message_id: waitMsg.message_id }); } catch (_) {}
        }
        return;
      }
    } catch (e) {
      console.error('TikTok error:', e);
    }
  }

  // 2. Active Multi-Cloud Extractors (Modern Cobalt v10/v11 API)
  const extractors = [
    'https://rue-cobalt.xenon.zone/',
    'https://cobaltapi.cjs.nz/'
  ];

  for (const ep of extractors) {
    try {
      const r = await fetch(ep, {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
          'User-Agent': 'Mozilla/5.0'
        },
        body: JSON.stringify({
          url: mediaUrl,
          videoQuality: '720'
        })
      });

      if (!r.ok) {
        console.warn(`[Extractor ${ep}] returned status ${r.status}`);
        continue;
      }

      const json = await r.json();
      if (json && (json.url || (json.picker && json.picker[0]?.url))) {
        const direct = json.url || json.picker[0].url;
        await api.sendVideo({
          chat_id: chatId,
          video: direct,
          caption: `🎬 <b>${escapeHtml(json.filename || 'فایل آماده شد / Ready to watch!')}</b>\n\n📡 @OneForAllHub`,
          parse_mode: 'HTML'
        });

        await recordDownload(chatId, mediaUrl, 'cloud-extractor');

        if (waitMsg && waitMsg.message_id) {
          try { await api.deleteMessage({ chat_id: chatId, message_id: waitMsg.message_id }); } catch (_) {}
        }
        return;
      }
    } catch (e) {
      console.error(`[Extractor ${ep}] error:`, e);
    }
  }

  // Fallback notification with direct Web App link
  await api.sendMessage({
    chat_id: chatId,
    parse_mode: 'HTML',
    text:
      `⚠️ دریافت مستقیم این ویدیو در تلگرام با محدودیت مواجه شد (احتمالاً ویدیو دارای محافظت کپی‌رایت یا حجم بیش از حد مجاز تلگرام است).\n\n` +
      `🌐 می‌توانید لینک را در <b>وب‌اپلیکیشن رایگان ما</b> یا ربات دانلود ابری باز کرده و دانلود کنید:\n` +
      `https://thehunterx.github.io/oneforall-media-downloader/\n\n` +
      `📡 @OneForAllHub`
  });

  if (waitMsg && waitMsg.message_id) {
    try { await api.deleteMessage({ chat_id: chatId, message_id: waitMsg.message_id }); } catch (_) {}
  }
}
