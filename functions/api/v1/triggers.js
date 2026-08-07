import { decodeCursor, encodeCursor, json, loadTriggerPayload, searchableText } from '../../_shared/trigger-data.js';

export async function onRequestOptions() {
  return json({ ok: true });
}

export async function onRequestGet(context) {
  try {
    const payload = await loadTriggerPayload(context);
    const url = new URL(context.request.url);
    const category = String(url.searchParams.get('category') || '').trim().toUpperCase();
    const sentiment = String(url.searchParams.get('sentiment') || '').trim().toLowerCase();
    const symbol = String(url.searchParams.get('symbol') || '').trim().toUpperCase();
    const query = String(url.searchParams.get('q') || '').trim().toLowerCase();
    const minImpact = Math.max(0, Math.min(100, Number(url.searchParams.get('minImpact') || 0)));
    const limit = Math.max(1, Math.min(100, Number(url.searchParams.get('limit') || 25)));
    const offset = decodeCursor(url.searchParams.get('cursor'));

    const all = Array.isArray(payload.triggers) ? payload.triggers : [];
    const filtered = all.filter((row) => {
      if (category && String(row.category || '').toUpperCase() !== category) return false;
      if (sentiment && String(row.sentiment || '').toLowerCase() !== sentiment) return false;
      if (symbol && String(row.symbol || '').toUpperCase() !== symbol) return false;
      if (Number(row.impactScore || 0) < minImpact) return false;
      if (query && !searchableText(row).includes(query)) return false;
      return true;
    });

    const items = filtered.slice(offset, offset + limit);
    const nextOffset = offset + items.length;
    return json({
      ok: true,
      updatedAt: payload.updatedAt || null,
      generatedAt: payload.generatedAt || null,
      sourceHealthy: Boolean(payload.sourceHealthy),
      sourceMode: payload.sourceMode || null,
      total: filtered.length,
      count: items.length,
      nextCursor: nextOffset < filtered.length ? encodeCursor(nextOffset) : null,
      items
    });
  } catch (error) {
    return json({ ok: false, error: error.message || 'Unable to load stock triggers.' }, 500, 'no-store');
  }
}
