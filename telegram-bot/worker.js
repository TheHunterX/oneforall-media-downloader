/**
 * OneForAllHub - Serverless Telegram Downloader Bot (Bilingual: English & Persian)
 * Runs 100% FREE on Cloudflare Workers (0 server / 0 VPS required)
 * Handles: TikTok (No watermark), Instagram Reels/Posts, YouTube, Twitter/X
 */

export default {
  async fetch(request, env) {
    if (request.method !== 'POST') {
      return new Response('OneForAllHub Downloader Bot is running!', { status: 200 });
    }

    try {
      const update = await request.json();
      if (!update.message || !update.message.text) {
        return new Response('OK');
      }

      const chatId = update.message.chat.id;
      const text = update.message.text.trim();
      const messageId = update.message.message_id;

      // Handle /start command (Bilingual)
      if (text.startsWith('/start')) {
        await sendTelegramMessage(env.BOT_TOKEN, chatId, 
          `👋 <b>سلام! به ربات دانلودر OneForAllHub خوش آمدید.</b>\n` +
          `<i>Welcome to OneForAllHub Media Downloader Bot.</i>\n\n` +
          `📥 <b>لینک ویدیو یا ریلز را ارسال کنید:</b>\n` +
          `<i>Send any video, reel or music link from:</i>\n\n` +
          `• <b>TikTok</b> (بدون واترمارک / No watermark)\n` +
          `• <b>Instagram</b> (ریلز و پست / Reels & Posts)\n` +
          `• <b>YouTube</b> (ویدیو و صوت / Video & Audio)\n` +
          `• <b>Twitter / X & Pinterest</b>\n\n` +
          `📡 <b>کانال ما / Official Channel:</b> @OneForAllHub`,
          { parse_mode: 'HTML' }
        );
        return new Response('OK');
      }

      // Check URL
      const urlMatch = text.match(/(https?:\/\/[^\s]+)/g);
      if (!urlMatch) {
        await sendTelegramMessage(env.BOT_TOKEN, chatId, 
          '⚠️ لطفاً یک لینک معتبر اینستاگرام، تیک‌تاک یا یوتیوب ارسال کنید.\n' +
          '<i>Please send a valid Instagram, TikTok, or YouTube link.</i>'
        );
        return new Response('OK');
      }

      const mediaUrl = urlMatch[0];
      const statusMsg = await sendTelegramMessage(env.BOT_TOKEN, chatId, 
        '⏳ <b>در حال پردازش و استخراج فایل... لطفاً صبر کنید.</b>\n' +
        '<i>Processing and extracting media... Please wait.</i>'
      );
      const statusMsgId = statusMsg?.result?.message_id;

      // 1. Process TikTok via TikWM (No Watermark)
      if (mediaUrl.includes('tiktok.com')) {
        try {
          const res = await fetch(`https://www.tikwm.com/api/?url=${encodeURIComponent(mediaUrl)}`, {
            headers: { 'User-Agent': 'Mozilla/5.0' }
          });
          const json = await res.json();
          if (json && json.code === 0 && json.data) {
            const videoUrl = json.data.play || json.data.wmplay;
            const caption = `🎬 <b>${escapeHtml(json.data.title || 'TikTok Video')}</b>\n\n` +
                            `👤 ${json.data.author?.nickname || ''} (@${json.data.author?.unique_id || 'TikTok'})\n` +
                            `✨ <i>No Watermark HD</i>\n\n` +
                            `📡 @OneForAllHub`;
            
            await sendTelegramVideo(env.BOT_TOKEN, chatId, videoUrl, caption);
            if (statusMsgId) await deleteTelegramMessage(env.BOT_TOKEN, chatId, statusMsgId);
            return new Response('OK');
          }
        } catch (e) {}
      }

      // 2. Multi-Cloud Cobalt Instances
      const COBALT_ENDPOINTS = [
        'https://api.cobalt.tools/',
        'https://cobalt.kwiatekm.pl/api/json',
        'https://capi.wuk.sh/api/json'
      ];

      let downloaded = false;
      for (const endpoint of COBALT_ENDPOINTS) {
        try {
          const cobaltRes = await fetch(endpoint, {
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

          if (!cobaltRes.ok) continue;

          const data = await cobaltRes.json();
          if (data && (data.url || (data.picker && data.picker.length > 0))) {
            const targetUrl = data.url || data.picker[0].url;
            const caption = `🎬 <b>آماده شد / Ready to watch!</b>\n\n📡 @OneForAllHub`;
            
            await sendTelegramVideo(env.BOT_TOKEN, chatId, targetUrl, caption);
            downloaded = true;
            if (statusMsgId) await deleteTelegramMessage(env.BOT_TOKEN, chatId, statusMsgId);
            break;
          }
        } catch (e) {}
      }

      if (!downloaded) {
        await sendTelegramMessage(env.BOT_TOKEN, chatId, 
          '❌ دریافت مستقیم ناموفق بود. اگر ویدیو خصوصی (Private) باشد قابل دانلود نیست.\n' +
          'همچنین می‌توانید از وب‌سایت ما استفاده کنید:\n' +
          '🌐 https://thehunterx.github.io/oneforall-media-downloader/\n\n' +
          '<i>Direct download failed or media is private. You can also try our web app above.</i>'
        );
        if (statusMsgId) await deleteTelegramMessage(env.BOT_TOKEN, chatId, statusMsgId);
      }

      return new Response('OK');
    } catch (err) {
      return new Response('Error: ' + err.message, { status: 500 });
    }
  }
};

// Telegram API Helpers
async function sendTelegramMessage(botToken, chatId, text, options = {}) {
  const url = `https://api.telegram.org/bot${botToken}/sendMessage`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      chat_id: chatId,
      text: text,
      parse_mode: options.parse_mode || 'HTML'
    })
  });
  return await res.json();
}

async function sendTelegramVideo(botToken, chatId, videoUrl, caption) {
  const url = `https://api.telegram.org/bot${botToken}/sendVideo`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      chat_id: chatId,
      video: videoUrl,
      caption: caption,
      parse_mode: 'HTML'
    })
  });
  return await res.json();
}

async function deleteTelegramMessage(botToken, chatId, messageId) {
  const url = `https://api.telegram.org/bot${botToken}/deleteMessage`;
  await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, message_id: messageId })
  });
}

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
