import { fetch } from 'sdk';
import { db, sql } from 'sdk/db';

const REPO = 'TheHunterX/oneforall-media-downloader';
let _cachedToken = '';

/**
 * Retrieves the GitHub PAT from the private server-side SQLite vault on Telegram Cloud.
 * Zero credentials or keys are stored in the repository source code.
 */
export async function getGithubToken() {
  if (_cachedToken) return _cachedToken;
  try {
    const row = await db.get(sql`SELECT v FROM vault WHERE k = 'gh_pat'`);
    if (row && row.v) {
      _cachedToken = String(row.v).trim();
      return _cachedToken;
    }
  } catch (err) {
    console.error('Vault read error:', err);
  }
  return '';
}

/**
 * Dispatches the 10Gbps Cloud Downloader workflow on GitHub Actions using the server-side vault token.
 */
export async function dispatchCloudWorkflow({ url, format = 'video-720p', chatId = '', messageId = '', sendToTelegram = 'true' }) {
  const token = await getGithubToken();
  if (!token) {
    throw new Error('Server vault token unavailable');
  }
  const res = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/downloader.yml/dispatches`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Accept': 'application/vnd.github.v3+json',
      'Content-Type': 'application/json',
      'User-Agent': 'OneForAllHubBot'
    },
    body: JSON.stringify({
      ref: 'main',
      inputs: {
        url: String(url),
        format: String(format),
        chat_id: chatId ? String(chatId) : '',
        message_id: messageId ? String(messageId) : '',
        send_to_telegram: String(sendToTelegram)
      }
    })
  });
  return res.ok || res.status === 204;
}

const _urlCache = new Map();

/**
 * Stores long URLs with a short key to prevent Telegram 64-byte callback_data truncation.
 */
export async function storeShortUrl(url) {
  if (!url) return '';
  const key = Math.random().toString(36).substring(2, 10);
  _urlCache.set(key, url);
  try {
    await db.run(sql`CREATE TABLE IF NOT EXISTS url_cache (k TEXT PRIMARY KEY, u TEXT)`);
    await db.run(sql`INSERT OR REPLACE INTO url_cache (k, u) VALUES (${key}, ${url})`);
  } catch (_) {}
  return key;
}

/**
 * Resolves a short key back to the original URL.
 */
export async function resolveShortUrl(keyOrUrl) {
  if (!keyOrUrl) return '';
  const clean = String(keyOrUrl).trim();
  if (clean.startsWith('http://') || clean.startsWith('https://')) return clean;
  if (_urlCache.has(clean)) return _urlCache.get(clean);
  try {
    const row = await db.get(sql`SELECT u FROM url_cache WHERE k = ${clean}`);
    if (row && row.u) {
      _urlCache.set(clean, row.u);
      return row.u;
    }
  } catch (_) {}
  try {
    return decodeURIComponent(clean);
  } catch (_) {
    return clean;
  }
}
