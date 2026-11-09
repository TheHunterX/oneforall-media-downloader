/**
 * OneForAllHub - Serverless Telegram Downloader Bot
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

      // Handle /start command
      if (text.startsWith('/start')) {
        await sendTelegramMessage(env.BOT_TOKEN, chatId, 
          `👋 <b>سلام به ربات دانلودر OneForAllHub خوش آمدید!</b>\n\n` +
          `کافیست لینک ویدیو یا ریلز مورد نظر خود را از:\n` +
          `• <b>TikTok</b> (بدون واترمارک)\n` +
          `• <b>Instagram</b> (ریلز و پست)\n` +
          `• <b>YouTube</b> (کلیپ و موزیک)\n` +
          `• <b>Twitter / X</b>\n\n` +
          `همینجا بفرستید تا سریعاً فایل ویدیویی یا صوتی را تحویل بگیرید.\n\n` +
          `📡 <b>کانال ما:</b> @OneForAllHub`,
          { parse_mode: 'HTML' }
        );
        return new Response('OK');
      }

      // Check URL
      const urlMatch = text.match(/(https?:\/\/[^\s]+)/g);
      if (!urlMatch) {
        await sendTelegramMessage(env.BOT_TOKEN, chatId, '⚠️ لطفاً یک لینک معتبر اینستاگرام، تیک‌تاک یا یوتیوب ارسال کنید.');
        return new Response('OK');
      }

      const mediaUrl = urlMatch[0];
      const statusMsg = await sendTelegramMessage(env.BOT_TOKEN, chatId, '⏳ در حال دریافت و آماده‌سازی فایل... لطفاً چند لحظه صبر کنید.');
      const statusMsgId = statusMsg?.result?.message_id;

      // 1. Process TikTok
      if (mediaUrl.includes('tiktok.com')) {
        const res = await fetch(`https://www.tikwm.com/api/?url=${encodeURIComponent(mediaUrl)}`);
        const json = await res.json();
        if (json && json.code === 0 && json.data) {
          const videoUrl = json.data.play || json.data.wmplay;
          const caption = `🎬 <b>${escapeHtml(json.data.title || 'TikTok Video')}</b>\n\n👤 ${json.data.author?.nickname || ''} (@${json.data.author?.unique_id || ''})\n\n📡 @OneForAllHub`;
          
          await sendTelegramVideo(env.BOT_TOKEN, chatId, videoUrl, caption);
          if (statusMsgId) await deleteTelegramMessage(env.BOT_TOKEN, chatId, statusMsgId);
          return new Response('OK');
        }
      }

      // 2. Process Instagram, YouTube, Twitter via Cobalt Serverless APIs
      const COBALT_ENDPOINTS = [
        'https://api.cobalt.tools/api/json',
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
            const caption = `🎬 <b>آماده شد!</b>\n\n📡 دانلود شده از @OneForAllHub`;
            
            await sendTelegramVideo(env.BOT_TOKEN, chatId, targetUrl, caption);
            downloaded = true;
            if (statusMsgId) await deleteTelegramMessage(env.BOT_TOKEN, chatId, statusMsgId);
            break;
          }
        } catch (e) {
          // Try next endpoint
        }
      }

      if (!downloaded) {
        await sendTelegramMessage(env.BOT_TOKEN, chatId, '❌ متأسفانه دریافت این لینک با خطا مواجه شد. لطفاً اطمینان حاصل کنید پیج یا ویدیو عمومی (Public) باشد.');
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
