/**
 * Comprehensive +18 / Porn / Adult Site & Subreddit URL Blocker
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
  'threads.net', 'threads.com', 'bsky.app', 'aparat.com', 'bilibili.com'
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
  'leakedzone.com', 'desiwood.online', 'tokyomotion.net', 'thisvid.com',
  'porntube.com', 'peekvids.com', 'lobstertube.com',
  'pimpbunny.com', 'tranny.one', 'tsplayground.com', 'grooby.com',
  'porniran.com', 'shahvani.com', 'iraniansex.com', 'superirani.com',
  'persianporn.com', 'sekshot.com'
]);

const ADULT_HOST_KEYWORDS = [
  'porn', 'xnxx', 'xvideos', 'xhamster', 'redtube', 'youjizz', 'spankbang',
  'hentai', 'rule34', 'chaturbate', 'stripchat', 'onlyfans', 'fansly',
  'redgif', 'erome', 'brazzers', 'xxx', 'sexvid', 'xvid', 'javhd', 'missav',
  'eporner', 'beeg', 'motherless', 'fapello', 'thothub', 'leakedzone',
  'pimpbunny', 'tranny', 'camgirl', 'livecam', 'slut', 'milf', 'boobs',
  'pussy', 'shemale', 'bdsm'
];

const ADULT_TLDS = ['.xxx', '.porn', '.sex', '.adult'];

// Substring check on /r/<subreddit> name (catches r/RedGIFsTrans, r/NSFW_GIF, r/IranianNSFW, etc.)
const NSFW_SUBREDDIT_KEYWORDS = [
  'nsfw', 'porn', 'redgif', 'xxx', 'hentai', 'rule34', 'gonewild', 'realgirls',
  'slut', 'milf', 'boobs', 'tiddies', 'booty', 'cumslut', 'pussy', 'fuck',
  'nude', 'naked', 'jerkoff', 'onlyfans', 'fansly', 'thot', 'shemale',
  'sissy', 'bdsm', 'fetish', 'yiff', 'ecchi', 'blowjob', 'handjob',
  'gangbang', 'creampie', 'escort'
];
const NSFW_EXACT_SUBS = new Set(['sex', 'ass', 'anal', 'cum', 'dick', 'cock', 'tits', 'boob', 'fap', 'leaks']);

// URL path token check for unknown websites/blogs (e.g. desiwood.online/...-full-nude-video/)
const ADULT_PATH_REGEX = /(?:^|[-_/])(?:porn|xxx|xnxx|xvideos|nude|naked|sexvideo|hentai|onlyfans|redgifs?|blowjob|handjob|gangbang|chudai|camgirl|brazzers|pussy|boobs)(?:[-_/]|$)/i;

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

  // Check Reddit subreddit name for any NSFW/porn substring
  if (host === 'reddit.com' || host.endsWith('.reddit.com')) {
    const subMatch = pathname.match(/^\/r\/([a-z0-9_]+)/i);
    if (subMatch && subMatch[1]) {
      const subLow = subMatch[1].toLowerCase();
      if (NSFW_EXACT_SUBS.has(subLow) || NSFW_SUBREDDIT_KEYWORDS.some(kw => subLow.includes(kw))) {
        return true;
      }
    }
    return false;
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

  // Path keyword check on non-whitelisted unknown blogs/sites
  if (ADULT_PATH_REGEX.test(pathname)) {
    return true;
  }

  return false;
}
