import { json, loadTriggerPayload } from '../../_shared/trigger-data.js';

export async function onRequestOptions() {
  return json({ ok: true });
}

export async function onRequestGet(context) {
  try {
    const payload = await loadTriggerPayload(context);
    const counts = payload.summary && payload.summary.categoryCounts ? payload.summary.categoryCounts : {};
    const categories = (Array.isArray(payload.categories) ? payload.categories : []).map((category) => ({
      ...category,
      count: Number(counts[category.label] || 0),
      url: `/stock-triggers/category/${String(category.id || '').toLowerCase().replace(/_/g, '-')}/`
    }));
    return json({ ok: true, updatedAt: payload.updatedAt || null, categories });
  } catch (error) {
    return json({ ok: false, error: error.message || 'Unable to load categories.' }, 500, 'no-store');
  }
}
