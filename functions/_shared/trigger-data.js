export function json(data, status = 200, cacheControl = 'public, max-age=300') {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': cacheControl,
      'access-control-allow-origin': '*',
      'access-control-allow-methods': 'GET, OPTIONS',
      'access-control-allow-headers': 'Content-Type'
    }
  });
}

export async function loadAssetJson(context, pathname, fallback = null) {
  if (!context.env || !context.env.ASSETS) {
    throw new Error('Cloudflare ASSETS binding is unavailable. Deploy this folder as a Pages project with Functions enabled.');
  }
  const url = new URL(pathname, context.request.url);
  const response = await context.env.ASSETS.fetch(url);
  if (!response.ok) {
    if (fallback !== null) return fallback;
    throw new Error(`Asset ${pathname} returned HTTP ${response.status}`);
  }
  return response.json();
}

export async function loadTriggerPayload(context) {
  return loadAssetJson(context, '/market-data/stock-triggers.json', {
    updatedAt: null,
    generatedAt: null,
    sourceHealthy: false,
    summary: {},
    categories: [],
    triggers: []
  });
}

export function decodeCursor(value) {
  if (!value) return 0;
  try {
    const decoded = atob(String(value).replace(/-/g, '+').replace(/_/g, '/'));
    const offset = Number(decoded);
    return Number.isFinite(offset) && offset >= 0 ? Math.floor(offset) : 0;
  } catch (error) {
    return 0;
  }
}

export function encodeCursor(offset) {
  return btoa(String(offset)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

export function normaliseSymbol(value) {
  return String(value || '').trim().toUpperCase();
}

export function searchableText(row) {
  return [
    row.symbol,
    row.stockName,
    row.companyName,
    row.subject,
    row.summary,
    row.categoryLabel,
    row.sentiment,
    ...(Array.isArray(row.highlights) ? row.highlights : [])
  ].join(' ').toLowerCase();
}
