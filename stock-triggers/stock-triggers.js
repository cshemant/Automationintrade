(function () {
  'use strict';

  const DATA_URL = '/market-data/stock-triggers.json';
  const PAGE_SIZE = 24;
  const elements = {
    title: document.getElementById('triggerPageTitle'),
    freshness: document.getElementById('triggerFreshness'),
    updated: document.getElementById('triggerUpdated'),
    total: document.getElementById('triggerTotal'),
    stocks: document.getElementById('triggerStocks'),
    highImpact: document.getElementById('triggerHighImpact'),
    sentimentMetric: document.getElementById('triggerSentiment'),
    sourceStatus: document.getElementById('triggerSourceStatus'),
    search: document.getElementById('triggerSearch'),
    category: document.getElementById('triggerCategory'),
    sentiment: document.getElementById('triggerSentimentFilter'),
    window: document.getElementById('triggerWindow'),
    sort: document.getElementById('triggerSort'),
    watchlistOnly: document.getElementById('triggerWatchlistOnly'),
    activeFilter: document.getElementById('triggerActiveFilter'),
    count: document.getElementById('triggerResultCount'),
    feed: document.getElementById('triggerFeed'),
    loadMore: document.getElementById('triggerLoadMore'),
    dialog: document.getElementById('triggerDialog'),
    dialogContent: document.getElementById('triggerDialogContent'),
    dialogClose: document.getElementById('triggerDialogClose')
  };

  if (!elements.feed) return;

  let payload = null;
  let rows = [];
  let filteredRows = [];
  let visibleCount = PAGE_SIZE;
  let forcedSymbol = '';
  let watchlistOnly = false;

  const esc = (value) => String(value == null ? '' : value).replace(/[&<>'"]/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  })[char]);


  function validHttpUrl(value) {
    const raw = String(value || '').trim();
    if (!raw) return '';
    try {
      const parsed = new URL(raw);
      return (parsed.protocol === 'https:' || parsed.protocol === 'http:') && parsed.hostname ? parsed.href : '';
    } catch (_error) {
      return '';
    }
  }

  function sourceAction(row) {
    const attachment = validHttpUrl(row.attachmentUrl);
    if (attachment) return { url: attachment, label: 'Original filing', direct: true };
    const sourceUrl = validHttpUrl(row.sourceUrl);
    const sourcePage = validHttpUrl(row.sourcePageUrl);
    const url = sourceUrl || sourcePage;
    if (!url) return { url: '', label: '', direct: false };
    const direct = row.sourceLinkType === 'original-filing' || /nsearchives\.nseindia\.com/i.test(url) || /\.(pdf|xml|zip)(?:$|[?#])/i.test(url);
    return { url, label: direct ? 'Original filing' : 'View on NSE', direct };
  }

  const number = (value) => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  };

  function formatPrice(value) {
    const parsed = number(value);
    if (parsed === null) return '';
    return '₹' + parsed.toLocaleString('en-IN', { maximumFractionDigits: 2 });
  }

  function formatChange(value) {
    const parsed = number(value);
    if (parsed === null) return '';
    const sign = parsed > 0 ? '+' : '';
    return `${sign}${parsed.toFixed(2)}%`;
  }

  function parseDate(value) {
    if (!value) return null;
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function daysFromToday(row) {
    const reference = parseDate(row.actionDate || row.publishedAt);
    if (!reference) return null;
    const now = new Date();
    now.setHours(0, 0, 0, 0);
    reference.setHours(0, 0, 0, 0);
    return Math.round((reference - now) / 86400000);
  }

  function relativeDate(row) {
    const days = daysFromToday(row);
    if (days === null) return row.publishedDisplay || 'Date unavailable';
    if (row.actionDate) {
      if (days === 0) return 'Action today';
      if (days > 0) return `Action in ${days} day${days === 1 ? '' : 's'}`;
      return `Action ${Math.abs(days)} day${Math.abs(days) === 1 ? '' : 's'} ago`;
    }
    if (days === 0) return 'Published today';
    if (days === -1) return 'Published yesterday';
    if (days < 0) return `Published ${Math.abs(days)} days ago`;
    return row.publishedDisplay || 'Latest filing';
  }

  function sentimentClass(value) {
    const label = String(value || 'Neutral').toLowerCase();
    if (label === 'positive') return 'is-positive';
    if (label === 'caution') return 'is-caution';
    if (label === 'mixed') return 'is-mixed';
    return 'is-neutral';
  }

  function scoreClass(score) {
    const value = number(score) || 0;
    if (value >= 75) return 'high';
    if (value >= 55) return 'medium';
    return 'low';
  }

  function scoreBreakdownTemplate(row) {
    const parts = Array.isArray(row.scoreBreakdown) ? row.scoreBreakdown : [];
    if (!parts.length) return '<p>Detailed score factors are unavailable for this legacy record.</p>';
    return `<div class="stock-trigger-dialog-score-list">${parts.map((part) => {
      const score = Math.max(0, number(part.score) || 0);
      const maximum = Math.max(1, number(part.max) || 1);
      const width = Math.min(100, Math.round(score * 100 / maximum));
      return `<article><div><strong>${esc(part.label || 'Factor')}</strong><span>${score}/${maximum}</span></div><div class="stock-trigger-dialog-score-track"><i style="width:${width}%"></i></div><p>${esc(part.reason || '')}</p></article>`;
    }).join('')}</div>`;
  }

  function freshnessText() {
    if (!payload) return 'Unavailable';
    const generated = parseDate(payload.generatedAt);
    if (!generated) return payload.sourceHealthy ? 'Updated' : 'Fallback mode';
    const hours = Math.max(0, Math.round((Date.now() - generated.getTime()) / 3600000));
    if (hours <= 6) return 'Fresh';
    if (hours <= 30) return 'Updated today';
    return `${Math.round(hours / 24)} days old`;
  }

  function renderSummary() {
    const summary = payload && payload.summary ? payload.summary : {};
    elements.total.textContent = Number(summary.totalTriggers || rows.length).toLocaleString('en-IN');
    elements.stocks.textContent = Number(summary.trackedStocks || new Set(rows.map((r) => r.symbol)).size).toLocaleString('en-IN');
    elements.highImpact.textContent = Number(summary.highImpactCount || rows.filter((r) => Number(r.impactScore) >= 75).length).toLocaleString('en-IN');
    elements.sentimentMetric.textContent = `${Number(summary.positiveCount || 0)} / ${Number(summary.cautionCount || 0)}`;
    elements.freshness.textContent = freshnessText();
    elements.updated.textContent = payload.updatedAt ? `Generated ${payload.updatedAt}` : 'Update time unavailable';

    const healthy = Boolean(payload.sourceHealthy);
    elements.sourceStatus.className = `stock-trigger-source-status ${healthy ? 'is-healthy' : 'is-fallback'}`;
    elements.sourceStatus.innerHTML = healthy
      ? `<strong>Daily source healthy.</strong> ${esc(payload.sourceNote || 'Fresh trigger data loaded.')}`
      : `<strong>Fallback protection active.</strong> ${esc(payload.sourceNote || 'Previous trigger history has been preserved.')}`;
  }

  function populateCategories() {
    const categories = Array.isArray(payload.categories) ? payload.categories : [];
    const counts = payload.summary && payload.summary.categoryCounts ? payload.summary.categoryCounts : {};
    categories.forEach((category) => {
      if (!category || !category.id || !category.label) return;
      const option = document.createElement('option');
      option.value = category.id;
      option.textContent = counts[category.label] ? `${category.label} (${counts[category.label]})` : category.label;
      elements.category.appendChild(option);
    });
  }

  function matchesTimeWindow(row, days) {
    if (!days) return true;
    const delta = daysFromToday(row);
    if (delta === null) return true;
    if (row.actionDate) return delta >= -days && delta <= days;
    return delta <= 0 && delta >= -days;
  }

  function applyFilters() {
    const query = elements.search.value.trim().toLowerCase();
    const category = elements.category.value;
    const sentiment = elements.sentiment.value;
    const windowDays = Number(elements.window.value || 0);

    filteredRows = rows.filter((row) => {
      if (forcedSymbol && String(row.symbol || '').toUpperCase() !== forcedSymbol) return false;
      if (watchlistOnly) {
        const symbols = window.AITWatchlist ? window.AITWatchlist.getSymbols() : [];
        if (!symbols.includes(String(row.symbol || '').toUpperCase())) return false;
      }
      if (category && row.category !== category) return false;
      if (sentiment && row.sentiment !== sentiment) return false;
      if (!matchesTimeWindow(row, windowDays)) return false;
      if (!query) return true;
      const haystack = [row.symbol, row.stockName, row.companyName, row.subject, row.summary, row.categoryLabel, row.sentiment, ...(row.highlights || [])].join(' ').toLowerCase();
      return haystack.includes(query);
    });

    const sort = elements.sort.value;
    filteredRows.sort((a, b) => {
      if (sort === 'impact') return Number(b.impactScore || 0) - Number(a.impactScore || 0);
      if (sort === 'symbol') return String(a.stockName || a.symbol).localeCompare(String(b.stockName || b.symbol));
      const aAnnouncement = String(a.sourceType || '').includes('Announcement');
      const bAnnouncement = String(b.sourceType || '').includes('Announcement');
      if (aAnnouncement !== bAnnouncement) return aAnnouncement ? -1 : 1;
      if (!aAnnouncement && !bAnnouncement) {
        const aDays = daysFromToday(a);
        const bDays = daysFromToday(b);
        const safeA = aDays !== null && aDays >= 0 ? aDays : Number.MAX_SAFE_INTEGER;
        const safeB = bDays !== null && bDays >= 0 ? bDays : Number.MAX_SAFE_INTEGER;
        return safeA - safeB || Number(b.impactScore || 0) - Number(a.impactScore || 0);
      }
      const bd = parseDate(b.publishedAt) || new Date(0);
      const ad = parseDate(a.publishedAt) || new Date(0);
      return bd - ad || Number(b.impactScore || 0) - Number(a.impactScore || 0);
    });

    visibleCount = PAGE_SIZE;
    updateUrl();
    renderFeed();
  }

  function updateUrl() {
    const url = new URL(window.location.href);
    const query = elements.search.value.trim();
    if (query) url.searchParams.set('q', query); else url.searchParams.delete('q');
    if (elements.category.value) url.searchParams.set('category', elements.category.value); else url.searchParams.delete('category');
    if (elements.sentiment.value) url.searchParams.set('sentiment', elements.sentiment.value); else url.searchParams.delete('sentiment');
    if (forcedSymbol) url.searchParams.set('symbol', forcedSymbol); else url.searchParams.delete('symbol');
    window.history.replaceState({}, '', url);
  }

  function cardTemplate(row) {
    const score = number(row.impactScore) || 0;
    const change = number(row.changePct);
    const highlights = (row.highlights || []).slice(0, 4);
    const source = sourceAction(row);
    const sourceButton = source.url
      ? `<a class="btn btn-primary" href="${esc(source.url)}" target="_blank" rel="noopener noreferrer">${esc(source.label)}</a>`
      : '';
    const priceLine = row.cmp != null
      ? `<span class="stock-trigger-price">${esc(formatPrice(row.cmp))}${change !== null ? ` <em class="${change >= 0 ? 'positive' : 'negative'}">${esc(formatChange(change))}</em>` : ''}</span>`
      : '';
    return `<article class="stock-trigger-card" data-trigger-id="${esc(row.id)}">
      <div class="stock-trigger-card-top">
        <div class="stock-trigger-company">
          <a href="/stock-triggers/?symbol=${encodeURIComponent(row.symbol || '')}" class="stock-trigger-symbol">${esc(row.symbol || 'STOCK')}</a>
          <div><strong>${esc(row.stockName || row.companyName || row.symbol)}</strong>${priceLine}</div>
        </div>
        <div class="stock-trigger-impact ${scoreClass(score)}"><span>Materiality</span><strong>${score}</strong><small>${esc(row.materialityBand || '')}</small></div>
      </div>
      <div class="stock-trigger-badge-row">
        <span class="stock-trigger-category">${esc(row.categoryLabel || 'Material Update')}</span>
        <span class="stock-trigger-sentiment ${sentimentClass(row.sentiment)}">${esc(row.sentiment || 'Neutral')}</span>
        ${row.filingExtracted ? '<span class="stock-trigger-ai-badge">Official filing extract</span>' : (row.aiEnhanced ? '<span class="stock-trigger-ai-badge">AI enriched</span>' : '')}
        <button class="stock-trigger-follow-button" type="button" data-ait-follow-symbol="${esc(row.symbol || '')}" data-ait-follow-name="${esc(row.stockName || row.companyName || row.symbol || '')}">Follow ${esc(row.symbol || '')}</button>
      </div>
      <h3>${esc(row.subject || 'Corporate development')}</h3>
      <p class="stock-trigger-summary">${esc(row.summary || '')}</p>
      ${highlights.length ? `<div class="stock-trigger-highlights">${highlights.map((value) => `<span>${esc(value)}</span>`).join('')}</div>` : ''}
      <div class="stock-trigger-meta"><span>${esc(relativeDate(row))}</span><span>${esc(row.sourceType || 'Exchange filing')}</span></div>
      <div class="stock-trigger-actions">
        <button class="btn btn-secondary trigger-detail-button" type="button" data-trigger-id="${esc(row.id)}">Why it matters</button>
        <a class="btn btn-secondary" href="${esc(row.eventUrl || row.triggerUrl || '#')}">Full event</a>
        <a class="btn btn-secondary" href="${esc(row.stockHubUrl || row.profileUrl || '/technical-analysis/')}">Stock hub</a>
        ${sourceButton}
      </div>
    </article>`;
  }

  function renderFeed() {
    const visible = filteredRows.slice(0, visibleCount);
    const scope = forcedSymbol ? ` for ${forcedSymbol}` : '';
    elements.count.textContent = `${filteredRows.length.toLocaleString('en-IN')} trigger${filteredRows.length === 1 ? '' : 's'} found${scope}.`;

    if (forcedSymbol) {
      elements.activeFilter.hidden = false;
      elements.activeFilter.innerHTML = `<span>Stock timeline: <strong>${esc(forcedSymbol)}</strong></span><button type="button" id="clearForcedSymbol">Show all stocks</button>`;
      const clear = document.getElementById('clearForcedSymbol');
      if (clear) clear.addEventListener('click', () => {
        forcedSymbol = '';
        elements.title.textContent = 'What changed in a stock today—and why it matters';
        applyFilters();
      });
    } else {
      elements.activeFilter.hidden = true;
      elements.activeFilter.innerHTML = '';
    }

    if (!visible.length) {
      elements.feed.innerHTML = '<article class="stock-trigger-empty"><strong>No matching stock trigger found.</strong><span>Change the category, search or time window. The daily generator may also be in fallback mode.</span></article>';
      elements.loadMore.hidden = true;
      return;
    }

    elements.feed.innerHTML = visible.map(cardTemplate).join('');
    elements.loadMore.hidden = visibleCount >= filteredRows.length;
    elements.feed.querySelectorAll('.trigger-detail-button').forEach((button) => {
      button.addEventListener('click', () => openDialog(button.dataset.triggerId));
    });
    if (window.AITWatchlist) window.AITWatchlist.refresh();
  }

  function openDialog(id) {
    const row = rows.find((item) => String(item.id) === String(id));
    if (!row || !elements.dialog || !elements.dialogContent) return;
    elements.dialogContent.innerHTML = `
      <p class="eyebrow">${esc(row.categoryLabel || 'Stock Trigger')}</p>
      <h2>${esc(row.symbol)} — ${esc(row.subject)}</h2>
      <p class="stock-trigger-dialog-summary">${esc(row.summary || '')}</p>
      <div class="stock-trigger-dialog-grid">
        <article><span>Materiality score</span><strong>${esc(row.impactScore || '—')}/100</strong></article>
        <article><span>Materiality band</span><strong>${esc(row.materialityBand || 'Unclassified')}</strong></article>
        <article><span>Data confidence</span><strong>${esc(row.dataConfidence || '—')}/100</strong></article>
        <article><span>Classification</span><strong>${esc(row.sentiment || 'Neutral')}</strong></article>
        <article><span>Published</span><strong>${esc(row.publishedDisplay || relativeDate(row))}</strong></article>
      </div>
      <section><h3>Why this score</h3><p>${esc(row.scoreExplanation || '')}</p>${scoreBreakdownTemplate(row)}</section>
      <section><h3>Why it may matter</h3><p>${esc(row.whyItMatters || '')}</p></section>
      <section><h3>What to verify</h3><p>${esc(row.riskNote || '')}</p></section>
      <section><h3>Summary basis</h3><p>${esc(row.summaryBasis || (row.filingExtracted ? 'Official filing text' : 'Exchange announcement text'))}</p></section>
      <div class="stock-trigger-dialog-actions">${sourceAction(row).url ? `<a class="btn btn-primary" href="${esc(sourceAction(row).url)}" target="_blank" rel="noopener noreferrer">${esc(sourceAction(row).direct ? 'Open original filing' : 'View on NSE')}</a>` : ''}<a class="btn btn-secondary" href="${esc(row.profileUrl || '/technical-analysis/')}">Open technical profile</a></div>`;
    if (typeof elements.dialog.showModal === 'function') elements.dialog.showModal();
    else elements.dialog.setAttribute('open', '');
  }

  function hydrateFromUrl() {
    const params = new URLSearchParams(window.location.search);
    forcedSymbol = (params.get('symbol') || '').trim().toUpperCase();
    elements.search.value = params.get('q') || '';
    elements.category.value = params.get('category') || '';
    elements.sentiment.value = params.get('sentiment') || '';
    if (forcedSymbol) elements.title.textContent = `${forcedSymbol} stock trigger timeline`;
  }

  function attachEvents() {
    let searchTimer = null;
    elements.search.addEventListener('input', () => {
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(applyFilters, 160);
    });
    [elements.category, elements.sentiment, elements.window, elements.sort].forEach((input) => input.addEventListener('change', applyFilters));
    if (elements.watchlistOnly) {
      elements.watchlistOnly.addEventListener('click', () => {
        watchlistOnly = !watchlistOnly;
        elements.watchlistOnly.classList.toggle('is-active', watchlistOnly);
        elements.watchlistOnly.setAttribute('aria-pressed', watchlistOnly ? 'true' : 'false');
        applyFilters();
      });
      window.addEventListener('ait:watchlist-changed', () => {
        if (watchlistOnly) applyFilters();
      });
    }
    elements.loadMore.addEventListener('click', () => {
      visibleCount += PAGE_SIZE;
      renderFeed();
    });
    elements.dialogClose.addEventListener('click', () => elements.dialog.close());
    elements.dialog.addEventListener('click', (event) => {
      if (event.target === elements.dialog) elements.dialog.close();
    });
  }

  fetch(`${DATA_URL}?v=${Date.now()}`, { cache: 'no-store' })
    .then((response) => {
      if (!response.ok) throw new Error(`Trigger JSON returned HTTP ${response.status}`);
      return response.json();
    })
    .then((data) => {
      payload = data || {};
      rows = Array.isArray(payload.triggers) ? payload.triggers : [];
      renderSummary();
      populateCategories();
      hydrateFromUrl();
      attachEvents();
      applyFilters();
    })
    .catch((error) => {
      elements.freshness.textContent = 'Unavailable';
      elements.updated.textContent = 'The daily trigger JSON could not be loaded.';
      elements.sourceStatus.className = 'stock-trigger-source-status is-fallback';
      elements.sourceStatus.innerHTML = `<strong>Data file unavailable.</strong> ${esc(error.message)}`;
      elements.feed.innerHTML = '<article class="stock-trigger-empty"><strong>Stock triggers are temporarily unavailable.</strong><span>Run GenerateStockTriggersJson.py or the GitHub Actions market update to recreate the JSON file.</span></article>';
      elements.count.textContent = '0 triggers found.';
    });
})();
