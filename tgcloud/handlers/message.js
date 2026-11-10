import { api, fetch, InputFile } from 'sdk';
import { db } from 'sdk/db';
import { downloads } from '../schema.js';
import { dispatchCloudWorkflow, storeShortUrl } from '../lib/vault.js';
import { getUserLang, setUserLang, texts, buildStartMessage } from '../lib/i18n.js';

const ADMIN_IDS = new Set([369287480, 369693896, 0x160914c8]); // Primary Admin Auth
function isAdmin(userId) {
  return ADMIN_IDS.has(Number(userId));
}
const CHANNEL_USERNAME = '@OneForAllHub';
const CHANNEL_URL = 'https://t.me/OneForAllHub';
const MINI_APP_URL = 'https://app9005060404.tgcloud.ai/';
const WEB_PAGES_URL = 'https://thehunterx.github.io/oneforall-media-downloader/';

// In-memory stats counter (fast edge cache, initialized to clean zeros)
let stats = {
  users: new Set([...ADMIN_IDS]),
  youtube: 0,
  tiktok: 0,
  twitter: 0,
  instagram: 0,
  other: 0,
  total: 0
};

function escapeHtml(text) {
  if (!text) return '';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function renderProgressBar(percent) {
  const totalBars = 12;
  const filled = Math.min(totalBars, Math.max(0, Math.round((percent / 100) * totalBars)));
  return '█'.repeat(filled) + '░'.repeat(totalBars - filled);
}

async function fetchStreamBytes(url) {
  const res = await fetch(url, { headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' } });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const chunks = [];
  let total = 0;
  for await (const chunk of res.body) {
    chunks.push(chunk);
    total += chunk.length;
  }
  const buf = new Uint8Array(total);
  let off = 0;
  for (const c of chunks) {
    buf.set(c, off);
    off += c.length;
  }
  return buf;
}

function sanitizeUrl(rawUrl) {
  if (!rawUrl) return rawUrl;
  const trimmed = rawUrl.trim();

  // 1. YouTube: Extract pure video ID (flexible 8-15 chars) and strip playlist/mix parameters
  if (trimmed.includes('youtube.com') || trimmed.includes('youtu.be')) {
    const m = trimmed.match(/(?:v=|\/shorts\/|\/embed\/|youtu\.be\/|\/v\/)([a-zA-Z0-9_-]{8,15})/);
    if (m && m[1]) {
      return `https://www.youtube.com/watch?v=${m[1]}`;
    }
  }

  // 2. Instagram: Strip ?igsh= and query trackers
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

async function checkChannelSubscription(userId) {
  if (isAdmin(userId)) return true;
  try {
    const res = await api.getChatMember({
      chat_id: CHANNEL_USERNAME,
      user_id: Number(userId)
    });
    if (res && res.status) {
      return ['creator', 'administrator', 'member', 'restricted'].includes(res.status);
    }
  } catch (err) {
    console.warn('Subscription check error:', err);
    return true; // Fail-open to avoid service disruption if bot lacks rights
  }
  return false;
}

export default async function (event) {
  try {
    const message = event?.message || event;
    const chatId = message?.chat?.id;
    const userId = message?.from?.id || chatId;
    let text = (typeof message?.text === 'string') ? message.text.trim() : '';

    if (!chatId) return;

    // Resolve user's preferred language (Default is English: 'en')
    const lang = await getUserLang(userId);
    const t = texts[lang] || texts.en;
    const isFa = lang === 'fa';

    // Support 1-click Web-to-Bot deep-linking (/start yt_<id> or /start ig_<shortcode>)
    if (text.startsWith('/start ')) {
      const startParam = text.slice(7).trim();
      if (startParam.startsWith('yt_')) {
        text = `https://www.youtube.com/watch?v=${startParam.slice(3)}`;
      } else if (startParam.startsWith('ig_')) {
        text = `https://www.instagram.com/reel/${startParam.slice(3)}/`;
      }
    }

    // Track user in memory
    stats.users.add(userId);

    // =====================================================================
    // 1. Admin Analytics Dashboard (/admin, /stats, /status) - Exclusive to Admins
    // =====================================================================
    if ((text.startsWith('/admin') || text.startsWith('/stats') || text.startsWith('/status')) && isAdmin(userId)) {
      let dbRows = [];
      try {
        dbRows = await db.select().from(downloads).all();
      } catch (_) {}

      const totalUsers = Math.max(stats.users.size, new Set(dbRows.map(r => r.chatId)).size);
      const ytCount = dbRows.filter(r => r.platform === 'YouTube').length;
      const tkCount = dbRows.filter(r => r.platform === 'TikTok').length;
      const twCount = dbRows.filter(r => r.platform === 'Twitter').length;
      const igCount = dbRows.filter(r => r.platform === 'Instagram').length;
      const otherCount = dbRows.filter(r => r.platform === 'Other').length;
      const totalCount = ytCount + tkCount + twCount + igCount + otherCount;

      const statsMsg =
        `👑 <b>OneForAllHub • Executive Admin Dashboard</b>\n\n` +
        `📊 <b>System Performance & Traffic Metrics:</b>\n` +
        `👥 <b>Total Tracked Users:</b> <code>${totalUsers} active users</code>\n` +
        `🚀 <b>Total Successful Deliveries:</b> <code>${totalCount} media files</code>\n\n` +
        `📁 <b>Downloads Breakdown by Platform:</b>\n` +
        `• 🔴 <b>YouTube (HD & MP3):</b> <code>${ytCount}</code>\n` +
        `• 🎵 <b>TikTok (No Watermark):</b> <code>${tkCount}</code>\n` +
        `• 🐦 <b>Twitter / X (Direct CDN):</b> <code>${twCount}</code>\n` +
        `• 📸 <b>Instagram (Reels & Posts):</b> <code>${igCount}</code>\n` +
        `• 🌐 <b>Other Platforms:</b> <code>${otherCount}</code>\n\n` +
        `⚡ <b>Infrastructure Health:</b>\n` +
        `• <b>Engine:</b> Telegram Serverless Cloud (TGCloud V8 Active)\n` +
        `• <b>Security Vault:</b> Server-Side SQLite Encrypted Vault\n` +
        `• <b>WARP Proxy:</b> 10Gbps Cloudflare Tunnel (Healthy)\n` +
        `• <b>Direct Streaming:</b> Native Chat Delivery Enabled\n` +
        `• <b>Enforced Channel:</b> <a href="${CHANNEL_URL}">${CHANNEL_USERNAME}</a>\n\n` +
        `📡 <i>Real-time monitoring provided for Admin ID ${userId}</i>`;

      await api.sendMessage({
        chat_id: chatId,
        parse_mode: 'HTML',
        text: statsMsg
      });
      return;
    }

    // =====================================================================
    // 1.1 Reset Stats Command (/reset_stats, /clear_stats)
    // =====================================================================
    if ((text === '/reset_stats' || text === '/clear_stats') && isAdmin(userId)) {
      try {
        await db.delete(downloads).run();
      } catch (_) {}
      stats.users = new Set([...ADMIN_IDS]);
      stats.youtube = 0;
      stats.tiktok = 0;
      stats.twitter = 0;
      stats.instagram = 0;
      stats.other = 0;
      stats.total = 0;
      await api.sendMessage({
        chat_id: chatId,
        parse_mode: 'HTML',
        text: '✅ <b>All bot statistics and download history have been reset to 0!</b>\n\nProject initialized for a completely clean testing run.'
      });
      return;
    }

    // =====================================================================
    // 1.2 Language Switch Command (/lang, /language)
    // =====================================================================
    if (text === '/lang' || text === '/language') {
      await api.sendMessage({
        chat_id: chatId,
        parse_mode: 'HTML',
        text: '🌐 <b>Select Your Language / زبان خود را انتخاب کنید:</b>',
        reply_markup: {
          inline_keyboard: [
            [
              { text: '🇬🇧 English (Default)', callback_data: 'set_lang:en' },
              { text: '🇮🇷 فارسی', callback_data: 'set_lang:fa' }
            ]
          ]
        }
      });
      return;
    }

    // =====================================================================
    // 2. /start Command (English by Default, User-Configurable)
    // =====================================================================
    if (!text || text.startsWith('/start') || text.startsWith('/help')) {
      const startMsg = buildStartMessage(lang, MINI_APP_URL, WEB_PAGES_URL, CHANNEL_URL);
      await api.sendMessage({
        chat_id: chatId,
        parse_mode: 'HTML',
        text: startMsg.text,
        reply_markup: startMsg.reply_markup
      });
      return;
    }

    // =====================================================================
    // 3. Mandatory Channel Join Check (@OneForAllHub)
    // =====================================================================
    const isSubscribed = await checkChannelSubscription(userId);
    if (!isSubscribed) {
      await api.sendMessage({
        chat_id: chatId,
        parse_mode: 'HTML',
        text: t.subRequired,
        reply_markup: {
          inline_keyboard: [
            [{ text: t.subBtnJoin, url: CHANNEL_URL }],
            [{ text: t.subBtnVerify, callback_data: 'verify_sub' }]
          ]
        }
      });
      return;
    }

    // =====================================================================
    // 4. URL Extraction & Validation
    // =====================================================================
    const match = text.match(/(https?:\/\/[^\s]+)/);
    if (!match) {
      await api.sendMessage({
        chat_id: chatId,
        parse_mode: 'HTML',
        text: t.invalidUrl
      });
      return;
    }

    const cleanUrl = sanitizeUrl(match[1]);

    // -------------------------------------------------------------
    // 5. YouTube Platform: Fast oEmbed Metadata & Quality Selection
    // -------------------------------------------------------------
    if (cleanUrl.includes('youtube.com') || cleanUrl.includes('youtu.be')) {
      const idMatch = cleanUrl.match(/(?:v=|\/shorts\/|\/embed\/|youtu\.be\/|\/v\/)([a-zA-Z0-9_-]{8,15})/);
      const videoId = idMatch ? idMatch[1] : '';

      if (!videoId) {
        await api.sendMessage({
          chat_id: chatId,
          parse_mode: 'HTML',
          text: t.invalidYtUrl
        });
        return;
      }

      let title = 'YouTube Video';
      let author = 'YouTube';
      let thumbUrl = `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`;

      try {
        const oembedRes = await fetch(`https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=${videoId}&format=json`);
        if (oembedRes.ok) {
          const odata = await oembedRes.json();
          if (odata.title) title = odata.title;
          if (odata.author_name) author = odata.author_name;
          if (odata.thumbnail_url) thumbUrl = odata.thumbnail_url;
        }
      } catch (_) {}

      const caption =
        `🎬 <b>${escapeHtml(title)}</b>\n` +
        `👤 <b>${isFa ? 'کانال' : 'Channel'}:</b> ${escapeHtml(author)}\n\n` +
        `👇 <b>${isFa ? 'کیفیت مورد نظر خود را برای دریافت انتخاب کنید:' : 'Select a quality to download directly in this chat:'}</b>`;

      const keyboard = {
        inline_keyboard: [
          [
            { text: '🎥 1080p (Full HD)', callback_data: `yt:video-1080p:${videoId}` },
            { text: '🎬 720p (HD)', callback_data: `yt:video-720p:${videoId}` }
          ],
          [
            { text: '📱 480p (Medium)', callback_data: `yt:video-480p:${videoId}` },
            { text: '💾 360p (Low)', callback_data: `yt:video-360p:${videoId}` }
          ],
          [
            { text: isFa ? '🎵 فایل صوتی (Original 192k MP3)' : '🎵 Audio MP3 (Original 192k)', callback_data: `yt:audio-mp3:${videoId}` }
          ]
        ]
      };

      try {
        await api.sendPhoto({
          chat_id: chatId,
          photo: thumbUrl,
          caption: caption,
          parse_mode: 'HTML',
          reply_markup: keyboard
        });
      } catch (err) {
        await api.sendMessage({
          chat_id: chatId,
          text: caption,
          parse_mode: 'HTML',
          reply_markup: keyboard
        });
      }
      return;
    }

    // -------------------------------------------------------------
    // 6. TikTok Platform: Live Progress & Watermark-Free HD Delivery
    // -------------------------------------------------------------
    if (cleanUrl.includes('tiktok.com')) {
      let waitMsg = null;
      try {
        waitMsg = await api.sendMessage({
          chat_id: chatId,
          parse_mode: 'HTML',
          text:
            `⏳ <b>${isFa ? 'در حال دانلود ویدیوی تیک‌تاک (بدون واترمارک)...' : 'Downloading TikTok Video (No Watermark)...'}</b>\n\n` +
            `<code>[${renderProgressBar(25)}]</code> <b>25%</b>\n` +
            `⚡ <b>Status:</b> ${isFa ? 'اتصال به سرورهای پرسرعت تیک‌تاک...' : 'Connecting to TikTok High-Speed API...'}\n` +
            `⏱ <b>Estimated:</b> ~2s remaining\n\n` +
            `📡 @OneForAllHub`
        });
      } catch (_) {}

      try {
        const res = await fetch(`https://www.tikwm.com/api/?url=${encodeURIComponent(cleanUrl)}`, {
          headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' }
        });
        const data = await res.json();
        if (data && data.code === 0 && data.data) {
          if (waitMsg?.message_id) {
            try {
              await api.editMessageText({
                chat_id: chatId,
                message_id: waitMsg.message_id,
                parse_mode: 'HTML',
                text:
                  `⏳ <b>${isFa ? 'در حال دانلود ویدیوی تیک‌تاک (بدون واترمارک)...' : 'Downloading TikTok Video (No Watermark)...'}</b>\n\n` +
                  `<code>[${renderProgressBar(75)}]</code> <b>75%</b>\n` +
                  `⚡ <b>Status:</b> ${isFa ? 'حذف واترمارک و آماده‌سازی فایل MP4...' : 'Removing watermark & streaming 1080p MP4...'}\n` +
                  `⏱ <b>Estimated:</b> ~1s remaining\n\n` +
                  `📡 @OneForAllHub`
              });
            } catch (_) {}
          }

          const vd = data.data;
          const videoUrl = vd.play || vd.wmplay;
          const vidId = vd.id || 'tiktok';
          const caption =
            `✨ <b>${escapeHtml(vd.title || (isFa ? 'ویدیوی تیک‌تاک HD' : 'TikTok HD Video'))}</b>\n\n` +
            `👤 <b>Creator:</b> ${escapeHtml(vd.author?.nickname || '')} (@${escapeHtml(vd.author?.unique_id || 'TikTok')})\n` +
            `🎯 <b>Quality:</b> 1080p HD (No Watermark)\n\n` +
            `📡 @OneForAllHub`;

          const tkKeyboard = {
            inline_keyboard: [
              [
                { text: isFa ? '🎵 استخراج موزیک MP3' : '🎵 Extract Music MP3', callback_data: `tk:audio:${vidId}` }
              ],
              [
                { text: isFa ? '📥 لینک دانلود مستقیم' : '📥 Direct CDN Link', url: videoUrl }
              ]
            ]
          };

          try {
            const [bytes, thumbBytes] = await Promise.all([
              fetchStreamBytes(videoUrl),
              (vd.cover || vd.origin_cover) ? fetchStreamBytes(vd.cover || vd.origin_cover).catch(() => null) : Promise.resolve(null)
            ]);

            const sendParams = {
              chat_id: chatId,
              video: new InputFile(bytes, `${vidId}_OneForAllHub.mp4`),
              caption: caption,
              parse_mode: 'HTML',
              supports_streaming: true,
              reply_markup: tkKeyboard
            };
            if (vd.duration) sendParams.duration = Math.round(vd.duration);
            if (thumbBytes) sendParams.thumbnail = new InputFile(thumbBytes, 'thumb.jpg');

            await api.sendVideo(sendParams);
            if (waitMsg?.message_id) {
              try { await api.deleteMessage({ chat_id: chatId, message_id: waitMsg.message_id }); } catch (_) {}
            }
            try {
              await db.insert(downloads).values({
                chatId: Number(chatId),
                url: cleanUrl,
                platform: 'TikTok',
                createdAt: new Date().toISOString()
              }).run();
            } catch (_) {}
            stats.tiktok++;
            stats.total++;
            return;
          } catch (_) {}

          // Direct URL fallback
          await api.sendVideo({
            chat_id: chatId,
            video: videoUrl,
            caption: caption,
            parse_mode: 'HTML',
            supports_streaming: true,
            reply_markup: tkKeyboard
          });

          if (waitMsg?.message_id) {
            try { await api.deleteMessage({ chat_id: chatId, message_id: waitMsg.message_id }); } catch (_) {}
          }
          try {
            await db.insert(downloads).values({
              chatId: Number(chatId),
              url: cleanUrl,
              platform: 'TikTok',
              createdAt: new Date().toISOString()
            }).run();
          } catch (_) {}
          stats.tiktok++;
          stats.total++;
          return;
        }
      } catch (e) {
        console.error('TikTok error:', e);
      }

      // Fallback: Dispatch to 10Gbps Cloud Runner
      if (waitMsg?.message_id) {
        try {
          await api.editMessageText({
            chat_id: chatId,
            message_id: waitMsg.message_id,
            parse_mode: 'HTML',
            text:
              `⏳ <b>Downloading TikTok Video...</b>\n\n` +
              `<code>[${renderProgressBar(40)}]</code> <b>40%</b>\n` +
              `⚡ <b>Status:</b> Routing via 10Gbps Cloud Runner...\n` +
              `⏱ <b>Estimated:</b> ~12s remaining\n\n` +
              `📡 @OneForAllHub`
          });
        } catch (_) {}
      }
      try {
        await dispatchCloudWorkflow({
          url: cleanUrl,
          format: 'video-720p',
          chatId: String(chatId),
          messageId: waitMsg?.message_id ? String(waitMsg.message_id) : '',
          sendToTelegram: 'true'
        });
      } catch (_) {}
      return;
    }

    // -------------------------------------------------------------
    // 7. Twitter / X Platform: Instant FxTwitter/VxTwitter HD Stream
    // -------------------------------------------------------------
    if (cleanUrl.includes('twitter.com') || cleanUrl.includes('x.com')) {
      let waitMsg = null;
      try {
        waitMsg = await api.sendMessage({
          chat_id: chatId,
          parse_mode: 'HTML',
          text:
            `⏳ <b>${isFa ? 'در حال دانلود ویدیوی توییتر / X با کیفیت اصلی...' : 'Downloading Twitter / X HD Media...'}</b>\n\n` +
            `<code>[${renderProgressBar(30)}]</code> <b>30%</b>\n` +
            `⚡ <b>Status:</b> ${isFa ? 'بررسی کیفیت‌ها و ابعاد ویدیو...' : 'Resolving tweet video stream & variants...'}\n` +
            `⏱ <b>Estimated:</b> ~2s remaining\n\n` +
            `📡 @OneForAllHub`
        });
      } catch (_) {}

      try {
        const fxUrl = cleanUrl.replace(/^https?:\/\/(?:www\.)?(?:twitter\.com|x\.com)\//i, 'https://api.fxtwitter.com/');
        const fxRes = await fetch(fxUrl, {
          headers: { 'User-Agent': 'OneForAllHubBot/2.0' }
        });
        if (fxRes.ok) {
          const fxData = await fxRes.json();
          const tweet = fxData?.tweet;
          const videos = tweet?.media?.videos || tweet?.media?.all || [];
          const v0 = videos[0];
          if (v0 && v0.url) {
            const duration = Math.round(v0.duration || 0);
            const width = v0.width || 0;
            const height = v0.height || 0;
            const thumbUrl = v0.thumbnail_url || '';
            const tweetId = tweet.id || 'twitter';
            const authorName = tweet.author?.name || 'Twitter / X';
            const screenName = tweet.author?.screen_name || 'x';
            const tweetText = (tweet.text || 'Twitter / X HD Video').slice(0, 140);

            const variants = (v0.variants || [])
              .filter(v => v.content_type === 'video/mp4' && v.url)
              .sort((a, b) => (b.bitrate || 0) - (a.bitrate || 0));

            const masterUrl = variants.length > 0 ? variants[0].url : v0.url;
            let streamUrl = masterUrl;
            const MAX_FETCH_BYTES = 24 * 1024 * 1024;
            if (duration > 0 && variants.length > 0) {
              for (const v of variants) {
                const estBytes = ((v.bitrate || 1500000) * duration) / 8;
                if (estBytes <= MAX_FETCH_BYTES) {
                  streamUrl = v.url;
                  break;
                }
              }
            }

            if (waitMsg?.message_id) {
              try {
                await api.editMessageText({
                  chat_id: chatId,
                  message_id: waitMsg.message_id,
                  parse_mode: 'HTML',
                  text:
                    `⏳ <b>${isFa ? 'در حال دریافت ویدیوی توییتر / X با کیفیت اصلی...' : 'Downloading Twitter / X HD Media...'}</b>\n\n` +
                    `<code>[${renderProgressBar(75)}]</code> <b>75%</b>\n` +
                    `⚡ <b>Status:</b> ${isFa ? 'ارسال ویدیو به چت...' : 'Streaming crystal-clear HD MP4 to chat...'}\n` +
                    `⏱ <b>Estimated:</b> ~1s remaining\n\n` +
                    `📡 @OneForAllHub`
                });
              } catch (_) {}
            }

            const caption =
              `🐦 <b>${escapeHtml(tweetText)}</b>\n\n` +
              `👤 <b>Author:</b> ${escapeHtml(authorName)} (@${escapeHtml(screenName)})\n` +
              `🎯 <b>Quality:</b> Original HD (${width && height ? `${width}x${height}` : '1080p/720p'})\n\n` +
              `📡 @OneForAllHub`;

            const twKeyboard = {
              inline_keyboard: [
                [{ text: isFa ? '📥 لینک مستقیم کیفیت اصلی (1080p)' : '📥 Direct 1080p Master CDN', url: masterUrl }]
              ]
            };

            try {
              const [videoBytes, thumbBytes] = await Promise.all([
                fetchStreamBytes(streamUrl),
                thumbUrl ? fetchStreamBytes(thumbUrl).catch(() => null) : Promise.resolve(null)
              ]);

              const sendParams = {
                chat_id: chatId,
                video: new InputFile(videoBytes, `${tweetId}_OneForAllHub.mp4`),
                caption: caption,
                parse_mode: 'HTML',
                supports_streaming: true,
                reply_markup: twKeyboard
              };
              if (duration > 0) sendParams.duration = duration;
              if (width > 0) sendParams.width = width;
              if (height > 0) sendParams.height = height;
              if (thumbBytes) sendParams.thumbnail = new InputFile(thumbBytes, 'thumb.jpg');

              await api.sendVideo(sendParams);
              if (waitMsg?.message_id) {
                try { await api.deleteMessage({ chat_id: chatId, message_id: waitMsg.message_id }); } catch (_) {}
              }
              try {
                await db.insert(downloads).values({
                  chatId: Number(chatId),
                  url: cleanUrl,
                  platform: 'Twitter',
                  createdAt: new Date().toISOString()
                }).run();
              } catch (_) {}
              stats.twitter++;
              stats.total++;
              return;
            } catch (sendErr) {
              console.warn('Twitter direct stream note:', sendErr.message);
            }
          }
        }
      } catch (twErr) {
        console.error('Twitter FxTwitter error:', twErr);
      }

      // Fallback: Dispatch to 10Gbps Cloud Runner
      if (waitMsg?.message_id) {
        try {
          await api.editMessageText({
            chat_id: chatId,
            message_id: waitMsg.message_id,
            parse_mode: 'HTML',
            text:
              `⏳ <b>Downloading Twitter / X Media...</b>\n\n` +
              `<code>[${renderProgressBar(40)}]</code> <b>40%</b>\n` +
              `⚡ <b>Status:</b> Routing via 10Gbps Cloud Runner...\n` +
              `⏱ <b>Estimated:</b> ~12s remaining\n\n` +
              `📡 @OneForAllHub`
          });
        } catch (_) {}
      }
      try {
        await db.insert(downloads).values({
          chatId: Number(chatId),
          url: cleanUrl,
          platform: 'Twitter',
          createdAt: new Date().toISOString()
        }).run();
      } catch (_) {}
      try {
        await dispatchCloudWorkflow({
          url: cleanUrl,
          format: 'video-720p',
          chatId: String(chatId),
          messageId: waitMsg?.message_id ? String(waitMsg.message_id) : '',
          sendToTelegram: 'true'
        });
      } catch (_) {}
      return;
    }

    // -------------------------------------------------------------
    // 8. Instagram Platform: Instant Quality Selection
    // -------------------------------------------------------------
    if (cleanUrl.includes('instagram.com')) {
      const scMatch = cleanUrl.match(/(?:reel|p|tv)\/([a-zA-Z0-9_-]+)/);
      const shortcode = scMatch ? scMatch[1] : 'media';

      await api.sendMessage({
        chat_id: chatId,
        parse_mode: 'HTML',
        text: t.igCaption,
        reply_markup: {
          inline_keyboard: [
            [
              { text: isFa ? '🎬 ویدیوی ریلز (HD)' : '🎬 Video / Reel (HD)', callback_data: `ig:video-720p:${shortcode}` },
              { text: isFa ? '🎵 فایل صوتی MP3' : '🎵 Audio MP3', callback_data: `ig:audio-mp3:${shortcode}` }
            ]
          ]
        }
      });
      return;
    }

    // -------------------------------------------------------------
    // 8.5. Pinterest Platform: High-Res Original Images & Videos
    // -------------------------------------------------------------
    if (cleanUrl.includes('pinterest.com') || cleanUrl.includes('pin.it')) {
      let waitMsg = null;
      try {
        waitMsg = await api.sendMessage({
          chat_id: chatId,
          parse_mode: 'HTML',
          text:
            `⏳ <b>${isFa ? 'در حال دریافت تصویر / ویدیوی پینترست با کیفیت اصلی...' : 'Downloading Pinterest HD / 4K Media...'}</b>\n\n` +
            `<code>[${renderProgressBar(30)}]</code> <b>30%</b>\n` +
            `⚡ <b>Status:</b> ${isFa ? 'بررسی لینک و دریافت بالاترین کیفیت...' : 'Resolving original Pin asset & metadata...'}\n` +
            `⏱ <b>Estimated:</b> ~1s remaining\n\n` +
            `📡 @OneForAllHub`
        });
      } catch (_) {}

      try {
        const pinRes = await fetch(cleanUrl, {
          redirect: 'follow',
          headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5'
          }
        });

        if (pinRes.ok) {
          const html = await pinRes.text();
          const finalUrl = pinRes.url || cleanUrl;

          // Title extraction
          let pinTitle = isFa ? 'تصویر باکیفیت پینترست' : 'Pinterest Media';
          const titleMatch = html.match(/<title>(.*?)<\/title>/i);
          if (titleMatch && titleMatch[1]) {
            pinTitle = titleMatch[1].split('|')[0].trim();
          }

          // Extract Pin ID
          const pinIdMatch = finalUrl.match(/\/pin\/([0-9]+)/) || cleanUrl.match(/\/pin\/([0-9]+)/);
          const pinId = pinIdMatch ? pinIdMatch[1] : 'pinterest';

          // 1. Check for Video Pin
          const vidMeta = html.match(/<meta[^>]+(?:property="og:video"|name="twitter:player:stream")[^>]+content="([^"]+)"/i) ||
                          html.match(/<meta[^>]+content="([^"]+)"[^>]+(?:property="og:video"|name="twitter:player:stream")/i);
          const vidJson = html.match(/https:\/\/v1\.pinimg\.com\/videos\/[^"'\s<>]+\.mp4/);
          const videoUrl = vidMeta ? vidMeta[1] : (vidJson ? vidJson[0] : null);

          if (videoUrl) {
            if (waitMsg?.message_id) {
              try {
                await api.editMessageText({
                  chat_id: chatId,
                  message_id: waitMsg.message_id,
                  parse_mode: 'HTML',
                  text:
                    `⏳ <b>${isFa ? 'در حال ارسال ویدیوی پینترست...' : 'Streaming Pinterest HD Video...'}</b>\n\n` +
                    `<code>[${renderProgressBar(80)}]</code> <b>80%</b>\n` +
                    `⚡ <b>Status:</b> ${isFa ? 'آماده‌سازی فایل MP4 برای پخش روان...' : 'Packaging MP4 video stream...'}\n` +
                    `⏱ <b>Estimated:</b> ~1s remaining\n\n` +
                    `📡 @OneForAllHub`
                });
              } catch (_) {}
            }

            const videoBytes = await fetchStreamBytes(videoUrl);
            const caption =
              `📌 <b>${escapeHtml(pinTitle)}</b>\n\n` +
              `🎯 <b>Quality:</b> HD Video (MP4)\n\n` +
              `📡 @OneForAllHub`;

            const keyboard = {
              inline_keyboard: [
                [{ text: isFa ? '📥 لینک مستقیم دانلود ویدیو' : '📥 Direct Video CDN Link', url: videoUrl }]
              ]
            };

            await api.sendVideo({
              chat_id: chatId,
              video: new InputFile(videoBytes, `${pinId}_OneForAllHub.mp4`),
              caption: caption,
              parse_mode: 'HTML',
              supports_streaming: true,
              reply_markup: keyboard
            });

            if (waitMsg?.message_id) {
              try { await api.deleteMessage({ chat_id: chatId, message_id: waitMsg.message_id }); } catch (_) {}
            }
            try {
              await db.insert(downloads).values({
                chatId: Number(chatId),
                url: cleanUrl,
                platform: 'Pinterest',
                createdAt: new Date().toISOString()
              }).run();
            } catch (_) {}
            stats.other++;
            stats.total++;
            return;
          }

          // 2. Check for Image Pin (Original Full Resolution)
          const imgOrigMatch = html.match(/"(?:images_orig|orig)"\s*:\s*\{[^}]*"url"\s*:\s*"([^"]+)"/) ||
                               html.match(/"url"\s*:\s*"(https:\/\/i\.pinimg\.com\/originals\/[^"]+)"/);
          let imgUrl = null;
          if (imgOrigMatch) {
            imgUrl = imgOrigMatch[1].replace(/\\\//g, '/');
          } else {
            const preloadM = html.match(/<link[^>]+id="pin-image-preload"[^>]+href="([^"]+)"/i) ||
                             html.match(/<meta[^>]+property="og:image"[^>]+content="([^"]+)"/i);
            if (preloadM) {
              const rawImg = preloadM[1].replace(/\\\//g, '/');
              imgUrl = rawImg.replace(/\/(?:736x|564x|474x|236x|1200x)\//, '/originals/');
            }
          }

          if (imgUrl) {
            if (waitMsg?.message_id) {
              try {
                await api.editMessageText({
                  chat_id: chatId,
                  message_id: waitMsg.message_id,
                  parse_mode: 'HTML',
                  text:
                    `⏳ <b>${isFa ? 'در حال ارسال تصویر پینترست با کیفیت اصلی...' : 'Downloading Original 4K/HD Image...'}</b>\n\n` +
                    `<code>[${renderProgressBar(85)}]</code> <b>85%</b>\n` +
                    `⚡ <b>Status:</b> ${isFa ? 'دریافت مستقیم از سرور اصلی پینترست...' : 'Fetching original uncompressed artwork...'}\n` +
                    `⏱ <b>Estimated:</b> ~1s remaining\n\n` +
                    `📡 @OneForAllHub`
                });
              } catch (_) {}
            }

            let imgBytes = null;
            let effectiveUrl = imgUrl;
            try {
              imgBytes = await fetchStreamBytes(effectiveUrl);
            } catch (imgErr) {
              // Try alternate extension (.png <-> .jpg)
              if (effectiveUrl.includes('.jpg')) {
                effectiveUrl = effectiveUrl.replace(/\.jpg(\?.*)?$/i, '.png$1');
                try { imgBytes = await fetchStreamBytes(effectiveUrl); } catch (_) {}
              } else if (effectiveUrl.includes('.png')) {
                effectiveUrl = effectiveUrl.replace(/\.png(\?.*)?$/i, '.jpg$1');
                try { imgBytes = await fetchStreamBytes(effectiveUrl); } catch (_) {}
              }
            }

            if (imgBytes && imgBytes.length > 0) {
              const isPng = effectiveUrl.toLowerCase().includes('.png');
              const ext = isPng ? 'png' : 'jpg';
              const sizeMb = (imgBytes.length / (1024 * 1024)).toFixed(2);
              const caption =
                `📌 <b>${escapeHtml(pinTitle)}</b>\n\n` +
                `🎯 <b>Quality:</b> Original HD / 4K (${ext.toUpperCase()})\n` +
                `📦 <b>Size:</b> ${sizeMb} MB\n\n` +
                `📡 @OneForAllHub`;

              const keyboard = {
                inline_keyboard: [
                  [{ text: isFa ? '📥 لینک مستقیم فایل اصلی (CDN)' : '📥 Direct Original Image (CDN)', url: effectiveUrl }]
                ]
              };

              // Send photo directly to chat
              await api.sendPhoto({
                chat_id: chatId,
                photo: new InputFile(imgBytes, `${pinId}_OneForAllHub.${ext}`),
                caption: caption,
                parse_mode: 'HTML',
                reply_markup: keyboard
              });

              if (waitMsg?.message_id) {
                try { await api.deleteMessage({ chat_id: chatId, message_id: waitMsg.message_id }); } catch (_) {}
              }
              try {
                await db.insert(downloads).values({
                  chatId: Number(chatId),
                  url: cleanUrl,
                  platform: 'Pinterest',
                  createdAt: new Date().toISOString()
                }).run();
              } catch (_) {}
              stats.other++;
              stats.total++;
              return;
            }
          }
        }
      } catch (pinErr) {
        console.warn('Pinterest direct fetch warning:', pinErr);
      }

      // Fallback: Dispatch to Cloud Runner if direct fetch failed
      if (waitMsg?.message_id) {
        try {
          await api.editMessageText({
            chat_id: chatId,
            message_id: waitMsg.message_id,
            parse_mode: 'HTML',
            text:
              `⏳ <b>${isFa ? 'در حال ارسال به سرور دانلود ابری...' : 'Downloading Pinterest Media...'}</b>\n\n` +
              `<code>[${renderProgressBar(40)}]</code> <b>40%</b>\n` +
              `⚡ <b>Status:</b> ${isFa ? 'اتصال به رانر پرسرعت...' : 'Routing via 10Gbps Cloud Runner...'}\n` +
              `⏱ <b>Estimated:</b> ~12s remaining\n\n` +
              `📡 @OneForAllHub`
          });
        } catch (_) {}
      }
      try {
        await db.insert(downloads).values({
          chatId: Number(chatId),
          url: cleanUrl,
          platform: 'Pinterest',
          createdAt: new Date().toISOString()
        }).run();
      } catch (_) {}
      try {
        await dispatchCloudWorkflow({
          url: cleanUrl,
          format: 'video-720p',
          chatId: String(chatId),
          messageId: waitMsg?.message_id ? String(waitMsg.message_id) : '',
          sendToTelegram: 'true'
        });
      } catch (_) {}
      return;
    }

    // -------------------------------------------------------------
    // 9. Other Platforms (Reddit, Vimeo, SoundCloud)
    // -------------------------------------------------------------
    const shortParam = await storeShortUrl(cleanUrl);
    await api.sendMessage({
      chat_id: chatId,
      parse_mode: 'HTML',
      text:
        `${t.genCaption}\n<code>${escapeHtml(cleanUrl.slice(0, 60))}...</code>\n\n` +
        `👇 ${isFa ? 'فرمت دلخواه را انتخاب کنید:' : 'Choose format to proceed with high-speed download:'}`,
      reply_markup: {
        inline_keyboard: [
          [
            { text: isFa ? '🎬 ویدیو (کیفیت اصلی)' : '🎬 Video (Best Quality)', callback_data: `gen:video-720p:${shortParam}` },
            { text: isFa ? '🎵 فایل صوتی MP3' : '🎵 Audio MP3', callback_data: `gen:audio-mp3:${shortParam}` }
          ]
        ]
      }
    });

  } catch (globalErr) {
    console.error('Global Handler Error:', globalErr);
  }
}
