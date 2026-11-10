import { api, fetch, InputFile } from 'sdk';
import { db } from 'sdk/db';
import { downloads } from '../schema.js';
import { getGithubToken, dispatchCloudWorkflow, resolveShortUrl } from '../lib/vault.js';
import { getUserLang, setUserLang, texts, buildStartMessage } from '../lib/i18n.js';

const ADMIN_IDS = new Set([369287480, 369693896, 0x160914c8]); // Primary Admin Auth
function isAdmin(userId) {
  return ADMIN_IDS.has(Number(userId));
}
const CHANNEL_USERNAME = '@OneForAllHub';
const CHANNEL_URL = 'https://t.me/OneForAllHub';
const MINI_APP_URL = 'https://app9005060404.tgcloud.ai/';
const WEB_PAGES_URL = 'https://thehunterx.github.io/oneforall-media-downloader/';
const REPO = 'TheHunterX/oneforall-media-downloader';

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

async function updateStatusMessage(chatId, messageId, percent, statusText, remainingSec, title = 'Downloading Media...') {
  if (!messageId) return;
  const bar = renderProgressBar(percent);
  const text =
    `⏳ <b>${escapeHtml(title)}</b>\n\n` +
    `<code>[${bar}]</code> <b>${percent}%</b>\n` +
    `⚡ <b>Status:</b> ${statusText}\n` +
    `⏱ <b>Estimated:</b> ~${remainingSec}s remaining\n\n` +
    `📡 @OneForAllHub`;

  try {
    await api.editMessageCaption({
      chat_id: chatId,
      message_id: messageId,
      parse_mode: 'HTML',
      caption: text
    });
  } catch (capErr) {
    try {
      await api.editMessageText({
        chat_id: chatId,
        message_id: messageId,
        parse_mode: 'HTML',
        text: text
      });
    } catch (_) {}
  }
}

async function fetchSingleRange(url, rangeHeader) {
  const headers = { 'User-Agent': 'OneForAllBot' };
  if (rangeHeader) headers['Range'] = rangeHeader;
  const res = await fetch(url, { headers });
  if (!res.ok && res.status !== 206) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  const chunks = [];
  let total = 0;
  for await (const chunk of res.body) {
    chunks.push(chunk);
    total += chunk.length;
  }
  const buf = new Uint8Array(total);
  let off = 0;
  for (const c of chunks) { buf.set(c, off); off += c.length; }
  return buf;
}

async function fetchMediaBytes(url, totalSize = 0) {
  let loc = url;
  try {
    if (url.includes('github.com/')) {
      const ghRes = await fetch(url, { redirect: 'manual', headers: { 'User-Agent': 'OneForAllBot' } });
      loc = (ghRes && ghRes.headers && ghRes.headers.get('location')) || url;
    }
  } catch (_) {}

  const MAX_SINGLE = 25 * 1024 * 1024;
  if (!totalSize || totalSize <= MAX_SINGLE) {
    return await fetchSingleRange(loc, null);
  }
  const ranges = [];
  for (let start = 0; start < totalSize; start += MAX_SINGLE) {
    const end = Math.min(start + MAX_SINGLE - 1, totalSize - 1);
    ranges.push({ start, end });
  }
  const parts = await Promise.all(ranges.map(async ({ start, end }) => {
    const buf = await fetchSingleRange(loc, `bytes=${start}-${end}`);
    return { start, buf };
  }));
  const totalLen = parts.reduce((acc, p) => acc + p.buf.length, 0);
  const assembled = new Uint8Array(Math.max(totalSize, totalLen));
  for (const p of parts) {
    assembled.set(p.buf, p.start);
  }
  return assembled.subarray(0, totalLen);
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
    return true;
  }
  return false;
}

function parseMp4Duration(data) {
  try {
    const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
    const limit = Math.min(data.length - 32, 256 * 1024);
    for (let i = 0; i < limit; i++) {
      if (data[i] === 0x6D && data[i+1] === 0x76 && data[i+2] === 0x68 && data[i+3] === 0x64) {
        const ver = data[i + 4];
        if (ver === 0) {
          const timescale = view.getUint32(i + 16);
          const dur = view.getUint32(i + 20);
          if (timescale > 0) return Math.round(dur / timescale);
        } else if (ver === 1) {
          const timescale = view.getUint32(i + 24);
          const durHi = view.getUint32(i + 28);
          const durLo = view.getUint32(i + 32);
          const dur = (durHi * 0x100000000) + durLo;
          if (timescale > 0) return Math.round(dur / timescale);
        }
      }
    }
  } catch (_) {}
  return 0;
}

function parseMp3Duration(data) {
  try {
    let offset = 0;
    if (data.length > 10 && data[0] === 0x49 && data[1] === 0x44 && data[2] === 0x33) {
      const tagSize = ((data[6] & 0x7f) << 21) | ((data[7] & 0x7f) << 14) | ((data[8] & 0x7f) << 7) | (data[9] & 0x7f);
      offset = 10 + tagSize;
    }
    const bitrates = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0];
    for (let i = offset; i < Math.min(data.length - 4, offset + 16384); i++) {
      if (data[i] === 0xFF && (data[i+1] & 0xE0) === 0xE0) {
        const ver = (data[i+1] >> 3) & 3;
        const layer = (data[i+1] >> 1) & 3;
        const brIdx = (data[i+2] >> 4) & 15;
        const srIdx = (data[i+2] >> 2) & 3;
        if (ver === 3 && layer === 1 && brIdx > 0 && brIdx < 15 && srIdx < 3) {
          const brKbps = bitrates[brIdx];
          const audioBytes = Math.max(0, data.length - offset);
          return Math.max(1, Math.round((audioBytes * 8) / (brKbps * 1000)));
        }
      }
    }
    const audioBytes = Math.max(0, data.length - offset);
    return Math.max(1, Math.round((audioBytes * 8) / 192000));
  } catch (_) {
    return 0;
  }
}

async function deliverCachedMedia(chatId, messageId, matched, fmtLabel, isAudio, videoId = '') {
  const totalSize = matched.size || 0;
  const sizeMb = (totalSize / (1024 * 1024)).toFixed(1);
  const NL = String.fromCharCode(10);
  const cleanDisplayName = (matched.name || '')
    .replace(/\.(mp4|mkv|webm|mov)\.mp3$/i, '.mp3')
    .replace(/\.(mp3|m4a|aac)\.mp4$/i, '.mp4')
    .replace(/\.f(?:dash-[a-zA-Z0-9_-]+|[0-9]+)(?=\.[a-zA-Z0-9]+$)/i, '');

  const caption = [
    '✅ <b>Your Media is Ready!</b>',
    '',
    `📁 <b>File:</b> <code>${cleanDisplayName}</code>`,
    `🎯 <b>Quality:</b> <b>${fmtLabel}</b>`,
    `📦 <b>Size:</b> <b>${sizeMb} MB</b>`,
    '',
    '📡 @OneForAllHub'
  ].join(NL);

  const keyboard = {
    inline_keyboard: [
      [{ text: '📥 Direct Download File (High-Speed CDN)', url: matched.browser_download_url }]
    ]
  };

  if (totalSize > 0 && totalSize <= 50 * 1024 * 1024) {
    try {
      const allBytes = await fetchMediaBytes(matched.browser_download_url, totalSize);

      const filenameLow = cleanDisplayName.toLowerCase();
      const isExplicitVideo = filenameLow.endsWith('.mp4') || filenameLow.endsWith('.mkv') || filenameLow.endsWith('.webm') || filenameLow.endsWith('.mov');
      const isExplicitAudio = filenameLow.endsWith('.mp3') || filenameLow.endsWith('.m4a') || filenameLow.endsWith('.aac') || filenameLow.endsWith('.flac') || filenameLow.endsWith('.wav');
      const isExplicitImage = filenameLow.endsWith('.jpg') || filenameLow.endsWith('.jpeg') || filenameLow.endsWith('.png') || filenameLow.endsWith('.webp');
      const shouldSendAudio = !isExplicitVideo && !isExplicitImage && (isExplicitAudio || isAudio);

      let thumbBytes = null;
      if (videoId && !videoId.startsWith('http') && videoId.length === 11) {
        try {
          thumbBytes = await fetchSingleRange(`https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`, null);
        } catch (_) {}
      }

      const parsedDur = isExplicitVideo ? parseMp4Duration(allBytes) : (isExplicitAudio ? parseMp3Duration(allBytes) : 0);

      if (isExplicitImage) {
        await api.sendPhoto({
          chat_id: chatId,
          photo: new InputFile(allBytes, cleanDisplayName),
          caption: caption,
          parse_mode: 'HTML',
          reply_markup: keyboard
        });
      } else if (shouldSendAudio) {
        const audioParams = {
          chat_id: chatId,
          audio: new InputFile(allBytes, cleanDisplayName),
          caption: caption,
          parse_mode: 'HTML',
          performer: '@OneForAllHub',
          title: cleanDisplayName.replace(/_OneForAllHub\..*$/, ''),
          reply_markup: keyboard
        };
        if (parsedDur > 0) audioParams.duration = parsedDur;
        if (thumbBytes) audioParams.thumbnail = new InputFile(thumbBytes, 'thumb.jpg');
        await api.sendAudio(audioParams);
      } else {
        const videoParams = {
          chat_id: chatId,
          video: new InputFile(allBytes, cleanDisplayName),
          caption: caption,
          parse_mode: 'HTML',
          supports_streaming: true,
          reply_markup: keyboard
        };
        if (parsedDur > 0) videoParams.duration = parsedDur;
        if (thumbBytes) videoParams.thumbnail = new InputFile(thumbBytes, 'thumb.jpg');
        await api.sendVideo(videoParams);
      }

      if (messageId) {
        try {
          await api.deleteMessage({ chat_id: chatId, message_id: messageId });
        } catch (_) {
          try {
            await api.editMessageCaption({
              chat_id: chatId,
              message_id: messageId,
              parse_mode: 'HTML',
              caption: '✅ <b>100% Complete | Delivered below</b>' + NL + NL + '📡 @OneForAllHub'
            });
          } catch (_) {}
        }
      }
      return true;
    } catch (e) {
      console.warn('Direct stream cache deliver note:', e.message);
    }
  } else if (totalSize > 50 * 1024 * 1024) {
    const largeCaption = [
      '⚠️ <b>محدودیت تلگرام: فایل بالاتر از ۵۰ مگابایت</b>',
      '⚠️ <b>Telegram In-Chat File Limit Exceeded</b>',
      '',
      `📁 <b>فایل / File:</b> <code>${cleanDisplayName}</code>`,
      `🎯 <b>کیفیت / Quality:</b> <b>${fmtLabel}</b>`,
      `📦 <b>حجم / Size:</b> <b>${sizeMb} MB</b>`,
      '',
      '⚡ <b>توضیح:</b> طبق قوانین رسمی تلگرام، ربات‌ها اجازه ارسال فایل‌های بالاتر از ۵۰ مگابایت را درون چت ندارند.',
      'Telegram bot API restricts bots from sending files larger than 50MB directly in chat.',
      '',
      '🚀 <b>دانلود مستقیم یا استریم آنلاین با حداکثر سرعت:</b>',
      'روی دکمه زیر کلیک کنید تا فایل کامل بدون افت کیفیت دانلود یا آنلاین پخش شود:',
      'Click the high-speed CDN link below to download or stream full-quality instantly:',
      '',
      '📡 @OneForAllHub'
    ].join(NL);

    await api.sendMessage({
      chat_id: chatId,
      parse_mode: 'HTML',
      text: largeCaption,
      reply_markup: keyboard
    });
    if (messageId) {
      try {
        await api.deleteMessage({ chat_id: chatId, message_id: messageId });
      } catch (_) {}
    }
    return true;
  }
  return false;
}

async function checkReleaseCache(targetFilename) {
  try {
    const token = await getGithubToken();
    const headers = {
      'Accept': 'application/vnd.github.v3+json',
      'User-Agent': 'OneForAllHubBot'
    };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const relRes = await fetch(`https://api.github.com/repos/${REPO}/releases/tags/v1.0-media`, { headers });
    if (relRes.ok) {
      const relData = await relRes.json();
      const assets = relData.assets || [];
      return assets.find(a => a.name.toLowerCase() === targetFilename.toLowerCase()) || null;
    }
  } catch (_) {}
  return null;
}

export default async function (input, ctx) {
  try {
    const query = input;
    const callbackQueryId = query?.id;
    const data = query?.data || '';
    const message = query?.message;
    const chatId = message?.chat?.id || query?.from?.id;
    const userId = query?.from?.id || chatId;
    const messageId = message?.message_id;

    if (!chatId || !data) return;

    // Resolve user's preferred language (Default is English: 'en')
    const lang = await getUserLang(userId);
    const t = texts[lang] || texts.en;
    const isFa = lang === 'fa';

    // ==================================================================
    // Case -1: Choose / Set Language (choose_lang / set_lang:xx)
    // ==================================================================
    if (data === 'choose_lang') {
      try {
        await api.answerCallbackQuery({
          callback_query_id: callbackQueryId,
          text: '🌐 Language selection / تغییر زبان'
        });
      } catch (_) {}

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

    if (data.startsWith('set_lang:')) {
      const newLang = data.split(':')[1] === 'fa' ? 'fa' : 'en';
      await setUserLang(userId, newLang);
      const isNewFa = newLang === 'fa';

      try {
        await api.answerCallbackQuery({
          callback_query_id: callbackQueryId,
          text: isNewFa ? '✅ زبان به فارسی تغییر کرد.' : '✅ Language set to English.'
        });
      } catch (_) {}

      const startMsg = buildStartMessage(newLang, MINI_APP_URL, WEB_PAGES_URL, CHANNEL_URL);
      const confirmNotice = isNewFa
        ? '✅ <b>زبان ربات با موفقیت به فارسی تغییر کرد!</b>\n\n'
        : '✅ <b>Language successfully set to English!</b>\n\n';

      await api.sendMessage({
        chat_id: chatId,
        parse_mode: 'HTML',
        text: confirmNotice + startMsg.text,
        reply_markup: startMsg.reply_markup
      });
      return;
    }

    // ==================================================================
    // Case 0: Verify Channel Subscription (verify_sub)
    // ==================================================================
    if (data === 'verify_sub') {
      const isSub = await checkChannelSubscription(userId);
      if (isSub) {
        try {
          await api.answerCallbackQuery({
            callback_query_id: callbackQueryId,
            text: isFa ? '✅ عضویت تایید شد!' : '✅ Subscription verified!'
          });
        } catch (_) {}

        await api.sendMessage({
          chat_id: chatId,
          parse_mode: 'HTML',
          text: t.subVerified,
          reply_markup: {
            inline_keyboard: [
              [
                { text: t.btnMiniApp, web_app: { url: MINI_APP_URL } },
                { text: t.btnWebsite, url: WEB_PAGES_URL }
              ],
              [
                { text: t.btnLang, callback_data: 'choose_lang' }
              ]
            ]
          }
        });
      } else {
        try {
          await api.answerCallbackQuery({
            callback_query_id: callbackQueryId,
            text: t.subNotJoined,
            show_alert: true
          });
        } catch (_) {}
      }
      return;
    }

    // Acknowledge other callbacks immediately
    try {
      await api.answerCallbackQuery({
        callback_query_id: callbackQueryId,
        text: '⚡ Processing request...'
      });
    } catch (_) {}

    // ==================================================================
    // Case 1: YouTube format selection ("yt:<format>:<videoId>")
    // ==================================================================
    if (data.startsWith('yt:')) {
      const parts = data.split(':');
      const fmt = parts[1] || 'video-720p';
      const videoId = parts[2];
      const isAudio = fmt === 'audio-mp3';
      const ext = isAudio ? 'mp3' : 'mp4';
      const targetFilename = `${videoId}_OneForAllHub.${ext}`;
      const targetUrl = `https://www.youtube.com/watch?v=${videoId}`;

      let fmtLabel = 'Video 720p (HD)';
      if (fmt === 'video-1080p') fmtLabel = 'Video 1080p (Full HD)';
      else if (fmt === 'video-480p') fmtLabel = 'Video 480p (Medium)';
      else if (fmt === 'video-360p') fmtLabel = 'Video 360p (Low)';
      else if (isAudio) fmtLabel = 'Audio MP3 (Original 192k)';

      await updateStatusMessage(chatId, messageId, 25, '🚀 Booting 10Gbps Cloud Runner (allocating VM)...', 12, `Downloading ${fmtLabel}...`);

      try {
        await db.insert(downloads).values({
          chatId: Number(chatId),
          url: targetUrl,
          platform: 'YouTube',
          createdAt: new Date().toISOString()
        }).run();
      } catch (_) {}

      const matched = await checkReleaseCache(targetFilename);
      if (matched && matched.browser_download_url) {
        const ok = await deliverCachedMedia(chatId, messageId, matched, fmtLabel, isAudio, videoId);
        if (ok) return;
      }

      try {
        await dispatchCloudWorkflow({
          url: targetUrl,
          format: fmt,
          chatId: String(chatId),
          messageId: messageId ? String(messageId) : '',
          sendToTelegram: 'true'
        });
      } catch (err) {
        console.error('Dispatch error:', err);
      }
      return;
    }

    // ==================================================================
    // Case 2: TikTok audio extraction ("tk:audio:<id>")
    // ==================================================================
    if (data.startsWith('tk:audio:')) {
      const parts = data.split(':');
      const videoId = parts[2];
      const tikUrl = `https://www.tiktok.com/@user/video/${videoId}`;
      const title = 'Extracting TikTok Audio MP3...';

      // Create a separate temporary status message so we DO NOT delete the user's video message!
      let audioWaitMsg = null;
      try {
        audioWaitMsg = await api.sendMessage({
          chat_id: chatId,
          parse_mode: 'HTML',
          text:
            `⏳ <b>${title}</b>\n\n` +
            `<code>[${renderProgressBar(30)}]</code> <b>30%</b>\n` +
            `⚡ <b>Status:</b> Connecting to TikTok Audio API...\n` +
            `⏱ <b>Estimated:</b> ~2s remaining\n\n` +
            `📡 @OneForAllHub`
        });
      } catch (_) {}

      const waitId = audioWaitMsg?.message_id;

      try {
        const res = await fetch(`https://www.tikwm.com/api/?url=${encodeURIComponent(tikUrl)}`, {
          headers: { 'User-Agent': 'Mozilla/5.0' }
        });
        const d = await res.json();
        if (d && d.code === 0 && d.data && d.data.music) {
          if (waitId) {
            await updateStatusMessage(chatId, waitId, 75, 'Extracting original 192kbps audio track...', 1, title);
          }
          const vd = d.data;
          const musicUrl = vd.music;
          const caption =
            `🎵 <b>${escapeHtml(vd.title || 'TikTok Original Audio')}</b>\n` +
            `👤 <b>Creator:</b> @${escapeHtml(vd.author?.unique_id || 'TikTok')}\n` +
            `🎯 <b>Quality:</b> Audio MP3 (Original 192kbps)\n\n` +
            `📡 @OneForAllHub`;

          const [bytes, thumbBytes] = await Promise.all([
            fetchSingleRange(musicUrl, null),
            (vd.cover || vd.origin_cover) ? fetchSingleRange(vd.cover || vd.origin_cover, null).catch(() => null) : Promise.resolve(null)
          ]);

          const dur = vd.duration ? Math.round(vd.duration) : parseMp3Duration(bytes);
          const audioParams = {
            chat_id: chatId,
            audio: new InputFile(bytes, `${videoId}_OneForAllHub.mp3`),
            caption: caption,
            parse_mode: 'HTML',
            performer: `@${vd.author?.unique_id || 'OneForAllHub'}`,
            title: (vd.title || `TikTok_${videoId}`).slice(0, 60)
          };
          if (dur > 0) audioParams.duration = dur;
          if (thumbBytes) audioParams.thumbnail = new InputFile(thumbBytes, 'thumb.jpg');

          await api.sendAudio(audioParams);
          if (waitId) {
            try { await api.deleteMessage({ chat_id: chatId, message_id: waitId }); } catch (_) {}
          }
          try {
            await db.insert(downloads).values({
              chatId: Number(chatId),
              url: tikUrl,
              platform: 'TikTok',
              createdAt: new Date().toISOString()
            }).run();
          } catch (_) {}
          return;
        }
      } catch (tkErr) {
        console.error('TikTok audio extraction error:', tkErr);
        if (waitId) {
          try { await api.deleteMessage({ chat_id: chatId, message_id: waitId }); } catch (_) {}
        }
      }
      return;
    }

    // ==================================================================
    // Case 3: Instagram ("ig:<format>:<shortcode>")
    // ==================================================================
    if (data.startsWith('ig:')) {
      const parts = data.split(':');
      const fmt = parts[1] || 'video-720p';
      const shortcode = parts[2];
      const igUrl = `https://www.instagram.com/reel/${shortcode}/`;
      const isAudio = fmt === 'audio-mp3';
      const ext = isAudio ? 'mp3' : 'mp4';
      const targetFilename = `${shortcode}_OneForAllHub.${ext}`;
      const title = isAudio ? 'Downloading Instagram Audio MP3...' : 'Downloading Instagram Reel (HD)...';

      await updateStatusMessage(chatId, messageId, 25, '🚀 Booting 10Gbps Cloud Runner (allocating VM)...', 10, title);

      try {
        await db.insert(downloads).values({
          chatId: Number(chatId),
          url: igUrl,
          platform: 'Instagram',
          createdAt: new Date().toISOString()
        }).run();
      } catch (_) {}

      const matched = await checkReleaseCache(targetFilename);
      if (matched && matched.browser_download_url) {
        const ok = await deliverCachedMedia(chatId, messageId, matched, isAudio ? 'Audio MP3 (Original 192kbps)' : 'Instagram Reel (HD)', isAudio, shortcode);
        if (ok) return;
      }

      try {
        await dispatchCloudWorkflow({
          url: igUrl,
          format: fmt,
          chatId: String(chatId),
          messageId: messageId ? String(messageId) : '',
          sendToTelegram: 'true'
        });
      } catch (err) {
        console.error('Instagram dispatch error:', err);
      }
      return;
    }

    // ==================================================================
    // Case 4: General Platforms ("gen:<format>:<encodedUrl>")
    // ==================================================================
    if (data.startsWith('gen:')) {
      const parts = data.split(':');
      const fmt = parts[1] || 'video-720p';
      const rawParam = parts.slice(2).join(':');
      const rawUrl = await resolveShortUrl(rawParam);
      const isAudio = fmt === 'audio-mp3';
      const title = isAudio ? 'Downloading Audio MP3...' : 'Downloading Media (Best Quality)...';

      await updateStatusMessage(chatId, messageId, 25, '🚀 Booting 10Gbps Universal Cloud Engine (allocating VM)...', 12, title);

      try {
        await db.insert(downloads).values({
          chatId: Number(chatId),
          url: rawUrl,
          platform: 'Other',
          createdAt: new Date().toISOString()
        }).run();
      } catch (_) {}

      try {
        await dispatchCloudWorkflow({
          url: rawUrl,
          format: fmt,
          chatId: String(chatId),
          messageId: messageId ? String(messageId) : '',
          sendToTelegram: 'true'
        });
      } catch (err) {
        console.error('Universal dispatch error:', err);
      }
      return;
    }

  } catch (err) {
    console.error('Global Callback Query Error:', err);
  }
}
