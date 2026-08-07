import { json, loadAssetJson, loadTriggerPayload } from '../../_shared/trigger-data.js';

export async function onRequestOptions() {
  return json({ ok: true });
}

export async function onRequestGet(context) {
  try {
    const payload = await loadTriggerPayload(context);
    const jobRuns = await loadAssetJson(context, '/market-data/stock-trigger-job-runs.json', { runs: [] });
    const generatedAt = payload.generatedAt ? new Date(payload.generatedAt) : null;
    const ageMinutes = generatedAt && !Number.isNaN(generatedAt.getTime())
      ? Math.max(0, Math.round((Date.now() - generatedAt.getTime()) / 60000))
      : null;
    const healthy = Boolean(payload.sourceHealthy) && ageMinutes !== null && ageMinutes <= 36 * 60;
    return json({
      ok: true,
      healthy,
      sourceHealthy: Boolean(payload.sourceHealthy),
      sourceMode: payload.sourceMode || null,
      updatedAt: payload.updatedAt || null,
      generatedAt: payload.generatedAt || null,
      ageMinutes,
      summary: payload.summary || {},
      sourceError: payload.sourceError || null,
      latestJobRun: Array.isArray(jobRuns.runs) && jobRuns.runs.length ? jobRuns.runs[0] : null
    }, healthy ? 200 : 200, 'no-store');
  } catch (error) {
    return json({ ok: false, healthy: false, error: error.message || 'Health check failed.' }, 500, 'no-store');
  }
}
