import { db, EndpointError } from 'sdk';
import { downloads } from '../schema.js';
import { dispatchCloudWorkflow } from '../lib/vault.js';

export default async function (input, ctx) {
  const url = (input && typeof input.url === 'string') ? input.url.trim() : '';
  const format = (input && typeof input.format === 'string') ? input.format.trim() : 'video-720p';

  if (!url || !url.startsWith('http')) {
    throw new EndpointError('Invalid media URL provided.', { code: 'INVALID_URL' });
  }

  const userId = ctx?.initData?.user?.id || 0;
  let platform = 'Other';
  const low = url.toLowerCase();
  if (low.includes('youtube.com') || low.includes('youtu.be')) platform = 'YouTube';
  else if (low.includes('tiktok.com')) platform = 'TikTok';
  else if (low.includes('twitter.com') || low.includes('x.com')) platform = 'Twitter';
  else if (low.includes('instagram.com')) platform = 'Instagram';
  else if (low.includes('pinterest.com') || low.includes('pin.it')) platform = 'Pinterest';

  try {
    await db.insert(downloads).values({
      chatId: Number(userId),
      url: url,
      platform: platform,
      createdAt: new Date().toISOString()
    }).run();
  } catch (_) {}

  const ok = await dispatchCloudWorkflow({
    url,
    format,
    chatId: input?.deliverToChat && userId ? String(userId) : '',
    messageId: '',
    sendToTelegram: input?.deliverToChat && userId ? 'true' : 'false'
  });

  if (!ok) {
    throw new EndpointError('Could not dispatch cloud runner.', { code: 'DISPATCH_FAILED' });
  }

  return { ok: true, dispatched: true, platform };
}
