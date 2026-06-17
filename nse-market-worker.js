/**
 * Cloudflare Worker: NSE market snapshot proxy
 * ------------------------------------------------------------
 * Why this is needed:
 * NSE blocks direct browser calls from normal websites through
 * CORS/session protection. Deploy this worker and route it as:
 *   https://automationintrade.com/api/nse-market
 *
 * Then the homepage can fetch /api/nse-market from the same domain.
 */

const NSE_HOME = 'https://www.nseindia.com/';
const NSE_ALL_INDICES = 'https://www.nseindia.com/api/allIndices';

const REQUIRED_INDICES = new Set([
  'NIFTY 50',
  'NIFTY BANK',
  'NIFTY MIDCAP SELECT',
  'INDIA VIX'
]);

function corsHeaders() {
  return {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'public, max-age=60',
    'access-control-allow-origin': '*'
  };
}

async function getNseCookies() {
  const response = await fetch(NSE_HOME, {
    headers: {
      'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome Safari',
      'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
      'accept-language': 'en-US,en;q=0.9'
    }
  });

  const rawCookie = response.headers.get('set-cookie') || '';
  return rawCookie.split(',').map(part => part.split(';')[0]).join('; ');
}

async function fetchNseIndices() {
  const cookie = await getNseCookies();

  const response = await fetch(NSE_ALL_INDICES, {
    headers: {
      'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome Safari',
      'accept': 'application/json,text/plain,*/*',
      'accept-language': 'en-US,en;q=0.9',
      'referer': NSE_HOME,
      'cookie': cookie
    }
  });

  if (!response.ok) {
    throw new Error(`NSE returned ${response.status}`);
  }

  const json = await response.json();
  const rows = Array.isArray(json.data) ? json.data : [];

  return rows
    .filter(row => REQUIRED_INDICES.has(String(row.index || '').toUpperCase()))
    .map(row => ({
      index: row.index,
      last: row.last,
      variation: row.variation,
      percentChange: row.percentChange,
      timestamp: row.timestamp || json.timestamp || null
    }));
}

export default {
  async fetch(request) {
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders() });
    }

    try {
      const data = await fetchNseIndices();
      return new Response(JSON.stringify({
        updatedAt: new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }),
        data
      }), { headers: corsHeaders() });
    } catch (error) {
      return new Response(JSON.stringify({
        error: true,
        message: error.message,
        data: []
      }), { status: 502, headers: corsHeaders() });
    }
  }
};
