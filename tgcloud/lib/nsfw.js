/**
 * Comprehensive +18 / Porn / Adult Site URL Blocker
 * Protects Telegram Bot, Mini App, Web UI, and Cloud Runner per Telegram Terms of Service.
 */

const SAFE_DOMAINS = [
  'youtube.com', 'youtu.be',
  'instagram.com', 'ddinstagram.com',
  'tiktok.com',
  'twitter.com', 'x.com', 'fxtwitter.com', 'vxtwitter.com', 'fixvx.com',
  'spotify.com', 'spotify.link', 'spoti.fi',
  'pinterest.com', 'pin.it',
  'soundcloud.com',
  'facebook.com', 'fb.watch',
  'vimeo.com', 'twitch.tv', 'dailymotion.com',
  'threads.net', 'bsky.app', 'aparat.com', 'bilibili.com'
];

const ADULT_DOMAINS = new Set([
  'pornhub.com', 'pornhubpremium.com', 'thumbzilla.com', 'redtube.com', 'youporn.com',
  'tube8.com', 'xtube.com', 'spankbang.com', 'spankwire.com', 'xvideos.com',
  'xvideos2.com', 'xvideos3.com', 'xnxx.com', 'xnxx2.com', 'xnxx3.com',
  'xhamster.com', 'xhamster2.com', 'xhamsterlive.com', 'xhcdn.com',
  'eporner.com', 'hqporner.com', 'beeg.com', 'tnaflix.com', 'empflix.com',
  'drtuber.com', 'sunporno.com', 'txxx.com', 'upornia.com', 'hdzog.com',
  'hotmovs.com', 'vjav.com', 'javhd.com', 'javmost.com', 'javguru.com',
  'missav.com', 'jable.tv', 'njav.tv', 'supjav.com', 'vlxx.sex',
  'brazzers.com', 'realitykings.com', 'bangbros.com', 'naughtyamerica.com',
  'mofos.com', 'digitalplayground.com', 'twistys.com', 'vixen.com',
  'blacked.com', 'tushy.com', 'teamskeet.com', 'evilangel.com', 'kink.com',
  'adulttime.com', 'dorcelclub.com', 'chaturbate.com', 'stripchat.com',
  'bongacams.com', 'cam4.com', 'myfreecams.com', 'livejasmin.com',
  'camsoda.com', 'flirt4free.com', 'streamate.com', 'imlive.com',
  'onlyfans.com', 'fansly.com', 'manyvids.com', 'clips4sale.com',
  'loyalfans.com', 'fapello.com', 'coomer.su', 'coomer.party',
  'kemono.su', 'kemono.party', 'simpcity.su', 'thothub.to', 'thothub.lol',
  'erome.com', 'bunkr.si', 'bunkr.ru', 'bunkr.is', 'redgifs.com',
  'gifdeliverynetwork.com', 'rule34.xxx', 'rule34video.com', 'e621.net',
  'nhentai.net', 'hanime.tv', 'hentaihaven.xxx', 'gelbooru.com',
  'sankakucomplex.com', 'iwara.tv', 'motherless.com', 'heavy-r.com',
  'efukt.com', 'daftsex.com', 'biqle.ru', 'sxyprn.com', 'porntrex.com',
  'pornone.com', 'pornhat.com', 'porndig.com', 'porngo.com', 'pornzog.com',
  'porn00.org', 'pornhd.com', 'fuq.com', 'gotporn.com', 'anyporn.com',
  '3movs.com', '4tube.com', 'fux.com', 'nuvid.com', 'slutload.com',
  'alphaporno.com', 'zbporn.com', 'analdin.com', 'youjizz.com', 'jizzbunker.com',
  'porniran.com', 'shahvani.com', 'iraniansex.com', 'superirani.com',
  'persianporn.com', 'sekshot.com'
]);

const ADULT_HOST_KEYWORDS = [
  'porn', 'xnxx', 'xvideos', 'xhamster', 'redtube', 'youjizz', 'spankbang',
  'hentai', 'rule34', 'chaturbate', 'stripchat', 'onlyfans', 'fansly',
  'redgifs', 'erome', 'brazzers', 'xxx', 'sexvid', 'xvid', 'javhd', 'missav',
  'eporner', 'beeg', 'motherless', 'fapello', 'thothub'
];

const ADULT_TLDS = ['.xxx', '.porn', '.sex', '.adult'];

const NSFW_REDDIT_SUBS = /\/r\/(?:nsfw|porn|gonewild|realgirls|hentai|rule34|sex|cumsluts|milf|boobs|ass|anal|blowjobs|nsfw_gif|nsfw_videos|iraniannsfw)(?:\/|$|\?)/i;

export function isNsfwUrl(rawUrl) {
  if (!rawUrl || typeof rawUrl !== 'string') return false;
  let host = '';
  let pathname = '';
  try {
    const parsed = new URL(rawUrl.trim());
    host = (parsed.hostname || '').toLowerCase().replace(/^www\./, '');
    pathname = (parsed.pathname || '').toLowerCase();
  } catch (_) {
    const m = rawUrl.trim().match(/^https?:\/\/([^/?#]+)(\/[^?#]*)?/i);
    if (!m) return false;
    host = (m[1] || '').toLowerCase().replace(/^www\./, '');
    pathname = (m[2] || '').toLowerCase();
  }
  if (!host) return false;

  // Check explicit NSFW subreddits on Reddit
  if (host === 'reddit.com' || host.endsWith('.reddit.com')) {
    return NSFW_REDDIT_SUBS.test(pathname);
  }

  // Allow verified mainstream platforms (e.g. x.com, youtube.com, instagram.com)
  for (const safe of SAFE_DOMAINS) {
    if (host === safe || host.endsWith('.' + safe)) {
      return false;
    }
  }

  // Adult TLDs (.xxx, .porn, .sex, .adult)
  for (const tld of ADULT_TLDS) {
    if (host.endsWith(tld)) return true;
  }

  // Exact or subdomain match against known +18 domains
  for (const dom of ADULT_DOMAINS) {
    if (host === dom || host.endsWith('.' + dom)) {
      return true;
    }
  }

  // Hostname keyword check (catches mirror/clone porn domains automatically)
  for (const kw of ADULT_HOST_KEYWORDS) {
    if (host.includes(kw)) {
      return true;
    }
  }

  return false;
}
