import { api } from 'sdk';

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
      text: '⚠️ لطفاً یک لینک معتبر از تیک‌تاک، اینستاگرام یا یوتیوب ارسال کنید.\n\nPlease send a valid video URL.'
    });
    return;
  }

  const mediaUrl = match[1];
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

        if (waitMsg && waitMsg.message_id) {
          try { await api.deleteMessage({ chat_id: chatId, message_id: waitMsg.message_id }); } catch (_) {}
        }
        return;
      }
    } catch (e) {
      console.error('TikTok error', e);
    }
  }

  // 2. Multi-Cloud Extractors for Instagram, YouTube, Twitter
  const extractors = [
    'https://api.cobalt.tools/',
    'https://cobalt.kwiatekm.pl/api/json',
    'https://capi.wuk.sh/api/json'
  ];

  for (const ep of extractors) {
    try {
      const r = await fetch(ep, {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          url: mediaUrl,
          vQuality: '720',
          filenamePattern: 'basic'
        })
      });

      if (!r.ok) continue;
      const json = await r.json();
      if (json && (json.url || (json.picker && json.picker[0]?.url))) {
        const direct = json.url || json.picker[0].url;
        await api.sendVideo({
          chat_id: chatId,
          video: direct,
          caption: `🎬 <b>فایل آماده شد / Ready to watch!</b>\n\n📡 @OneForAllHub`,
          parse_mode: 'HTML'
        });

        if (waitMsg && waitMsg.message_id) {
          try { await api.deleteMessage({ chat_id: chatId, message_id: waitMsg.message_id }); } catch (_) {}
        }
        return;
      }
    } catch (e) {}
  }

  // Fallback notification with direct Web App link
  await api.sendMessage({
    chat_id: chatId,
    parse_mode: 'HTML',
    text:
      `⚠️ دریافت مستقیم این ویدیو در تلگرام با محدودیت مواجه شد (احتمالاً پیج خصوصی است یا ویدیو بیش از حد مجاز حجم دارد).\n\n` +
      `🌐 می‌توانید لینک را در <b>وب‌اپلیکیشن رایگان ما</b> باز کرده و با حداکثر سرعت دانلود کنید:\n` +
      `https://thehunterx.github.io/oneforall-media-downloader/\n\n` +
      `📡 @OneForAllHub`
  });

  if (waitMsg && waitMsg.message_id) {
    try { await api.deleteMessage({ chat_id: chatId, message_id: waitMsg.message_id }); } catch (_) {}
  }
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
