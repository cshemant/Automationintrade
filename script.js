const year = document.getElementById('year');

if (year) {
  year.textContent = new Date().getFullYear();
}

// Mobile header menu (V97)
// - Desktop keeps the existing hover dropdowns.
// - Mobile hamburger opens the full menu. Tapping a dropdown heading opens its submenu
//   instead of navigating away, so every header link and tool menu remains reachable.
document.querySelectorAll('.site-header').forEach((header) => {
  const menuToggle = header.querySelector('.menu-toggle');
  const navLinks = header.querySelector('.nav-links');

  if (!menuToggle || !navLinks) return;

  if (!navLinks.querySelector('.mobile-home-link')) {
    const homeLink = document.createElement('a');
    homeLink.className = 'mobile-home-link';
    homeLink.href = '/';
    homeLink.textContent = 'Home';
    navLinks.prepend(homeLink);
  }

  const dropdowns = navLinks.querySelectorAll('.nav-dropdown');
  const dropdownTriggers = navLinks.querySelectorAll('.dropdown-trigger');

  function isMobileMenu() {
    return window.matchMedia('(max-width: 860px)').matches;
  }

  function closeSubmenus() {
    dropdowns.forEach((dropdown) => {
      dropdown.classList.remove('submenu-open');
      const trigger = dropdown.querySelector('.dropdown-trigger');
      if (trigger) trigger.setAttribute('aria-expanded', 'false');
    });
  }

  function syncMobileHeaderHeight() {
    if (!isMobileMenu()) return;
    const headerHeight = Math.ceil(header.getBoundingClientRect().height || 68);
    document.documentElement.style.setProperty('--mobile-header-height', `${headerHeight}px`);
  }

  function closeMobileMenu() {
    navLinks.classList.remove('open');
    menuToggle.classList.remove('is-active');
    menuToggle.setAttribute('aria-expanded', 'false');
    menuToggle.setAttribute('aria-label', 'Open menu');
    closeSubmenus();
    document.body.classList.remove('mobile-menu-open');
  }

  function openMobileMenu() {
    syncMobileHeaderHeight();
    navLinks.classList.add('open');
    menuToggle.classList.add('is-active');
    menuToggle.setAttribute('aria-expanded', 'true');
    menuToggle.setAttribute('aria-label', 'Close menu');
    document.body.classList.add('mobile-menu-open');
  }

  menuToggle.addEventListener('click', () => {
    if (navLinks.classList.contains('open')) {
      closeMobileMenu();
    } else {
      openMobileMenu();
    }
  });

  dropdownTriggers.forEach((trigger) => {
    trigger.addEventListener('click', (event) => {
      if (!isMobileMenu() || !navLinks.classList.contains('open')) return;

      event.preventDefault();
      const dropdown = trigger.closest('.nav-dropdown');
      const willOpen = !dropdown.classList.contains('submenu-open');

      dropdowns.forEach((item) => {
        if (item !== dropdown) {
          item.classList.remove('submenu-open');
          const itemTrigger = item.querySelector('.dropdown-trigger');
          if (itemTrigger) itemTrigger.setAttribute('aria-expanded', 'false');
        }
      });

      dropdown.classList.toggle('submenu-open', willOpen);
      trigger.setAttribute('aria-expanded', String(willOpen));
    });
  });

  navLinks.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', () => {
      const isDropdownHeading = link.classList.contains('dropdown-trigger');
      if (isMobileMenu() && isDropdownHeading) return;
      closeMobileMenu();
    });
  });

  document.addEventListener('click', (event) => {
    if (!navLinks.classList.contains('open')) return;
    if (header.contains(event.target)) return;
    closeMobileMenu();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeMobileMenu();
  });

  window.addEventListener('resize', () => {
    syncMobileHeaderHeight();
    if (!isMobileMenu()) closeMobileMenu();
  });

  syncMobileHeaderHeight();
});

const fullscreenBtn = document.getElementById('fullscreen-video-btn');
const demoVideoFrame = document.getElementById('demo-video-frame');

if (fullscreenBtn && demoVideoFrame) {
  fullscreenBtn.addEventListener('click', () => {
    if (demoVideoFrame.requestFullscreen) {
      demoVideoFrame.requestFullscreen();
    } else if (demoVideoFrame.webkitRequestFullscreen) {
      demoVideoFrame.webkitRequestFullscreen();
    }
  });
}

// NSE market snapshot strip
// Important: NSE does not allow reliable direct browser fetches from static sites
// because of CORS/session protection. This script first tries a same-origin
// endpoint (/api/nse-market), then a bundled static JSON file, then keeps the
// clean default values already printed in the HTML.
(function initNseMarketSnapshot() {
  const marketTiles = document.querySelectorAll('.market-tile[data-index]');
  const sourceNote = document.getElementById('market-source-note');

  if (!marketTiles.length) return;

  const endpoints = [
    '/api/nse-market',
    '/market-data/nse-snapshot.json'
  ];

  function formatNumber(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return '—';
    return num.toLocaleString('en-IN', { maximumFractionDigits: 2, minimumFractionDigits: 2 });
  }

  function formatChange(changeValue, percentChange) {
    const change = Number(changeValue);
    const pct = Number(percentChange);
    if (!Number.isFinite(change) || !Number.isFinite(pct)) {
      return { text: 'Latest snapshot', dir: 'muted' };
    }
    const sign = change >= 0 ? '+' : '';
    return {
      text: `${sign}${change.toFixed(2)} (${sign}${pct.toFixed(2)}%)`,
      dir: change >= 0 ? 'up' : 'down'
    };
  }

  function normalizeRows(payload) {
    if (!payload) return [];
    if (Array.isArray(payload)) return payload;
    if (Array.isArray(payload.data)) return payload.data;
    if (Array.isArray(payload.indices)) return payload.indices;
    return [];
  }

  function applySnapshot(payload, sourceLabel) {
    const rows = normalizeRows(payload);
    if (!rows.length) return false;

    let updatedCount = 0;

    marketTiles.forEach((tile) => {
      const indexName = (tile.dataset.index || '').toUpperCase();

      function normalizeIndexName(value) {
        const cleaned = String(value || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
        if (cleaned === 'NIFTYBANK' || cleaned === 'BANKNIFTY') return 'BANKNIFTY';
        if (cleaned === 'NIFTYMIDCAPSELECT' || cleaned === 'MIDCAPSELECT' || cleaned === 'MIDCPNIFTY') return 'MIDCAPSELECT';
        if (cleaned === 'NIFTY50' || cleaned === 'NIFTY') return 'NIFTY50';
        return cleaned;
      }

      const normalizedIndexName = normalizeIndexName(indexName);
      const row = rows.find((item) => {
        const name = item.index || item.indexName || item.name || item.symbol || '';
        return normalizeIndexName(name) === normalizedIndexName;
      });

      if (!row) return;

      const price = row.last || row.lastPrice || row.price || row.value;
      const change = row.variation || row.change || row.changeValue;
      // Support both live API keys and generated JSON keys.
      const percent = row.percentChange || row.pChange || row.changePercent || row.changePct;
      const changeInfo = formatChange(change, percent);

      const priceEl = tile.querySelector('.market-price');
      const changeEl = tile.querySelector('.market-change');

      if (priceEl) priceEl.textContent = formatNumber(price);
      if (changeEl) {
        changeEl.textContent = changeInfo.text;
        changeEl.classList.remove('up', 'down', 'muted');
        changeEl.classList.add(changeInfo.dir);
      }
      updatedCount += 1;
    });

    if (updatedCount > 0 && sourceNote) {
      const updatedAt = payload.updatedAt || payload.timestamp || '';
      sourceNote.textContent = updatedAt ? `${sourceLabel} • ${updatedAt}` : sourceLabel;
    }

    return updatedCount > 0;
  }

  async function fetchJson(url) {
    const separator = url.includes('?') ? '&' : '?';
    const response = await fetch(`${url}${separator}v=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async function updateMarketSnapshot() {
    for (const endpoint of endpoints) {
      try {
        const payload = await fetchJson(endpoint);
        const label = endpoint.includes('/api/') ? 'Live from NSE proxy' : 'Latest NSE snapshot';
        if (applySnapshot(payload, label)) return;
      } catch (error) {
        // Continue to next fallback.
      }
    }

    if (sourceNote) {
      sourceNote.textContent = 'Use included NSE proxy worker for automatic live updates';
    }
  }

  updateMarketSnapshot();
  window.setInterval(updateMarketSnapshot, 180000);
})();




// FII/DII activity snapshot for Market Tools homepage
(function () {
  const card = document.querySelector('[data-fii-dii-json]');
  if (!card) return;

  const jsonUrl = card.getAttribute('data-fii-dii-json');
  const headlineEl = document.getElementById('fiiDiiHeadline');
  const tbody = document.getElementById('fiiDiiTableBody');
  const updatedEl = document.getElementById('fiiDiiUpdated');

  function fmtCr(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return '-';
    return num.toLocaleString('en-IN', { maximumFractionDigits: 0 });
  }

  function fmtNet(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return '-';
    const sign = num > 0 ? '+' : '';
    return sign + num.toLocaleString('en-IN', { maximumFractionDigits: 0 });
  }

  function netClass(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return '';
    return num >= 0 ? 'net-positive' : 'net-negative';
  }

  function headlineNetClass(data, rows) {
    const headline = String(data.headline || '').toLowerCase();

    // Auto-colour rule:
    // Net Inflow / Net Buying  => green
    // Net Outflow / Net Selling => red
    // If the wording changes, fall back to total net value.
    if (headline.includes('outflow') || headline.includes('net selling') || headline.includes('net sell')) {
      return 'net-negative';
    }
    if (headline.includes('inflow') || headline.includes('net buying') || headline.includes('net buy')) {
      return 'net-positive';
    }

    const totalNet = rows.reduce((sum, row) => {
      const value = Number(row.netValue);
      return Number.isFinite(value) ? sum + value : sum;
    }, 0);
    return totalNet >= 0 ? 'net-positive' : 'net-negative';
  }

  function applyHeadlineColour(bannerClass) {
    if (!headlineEl) return;

    headlineEl.classList.remove('net-positive', 'net-negative');
    if (bannerClass) headlineEl.classList.add(bannerClass);

    // Use direct inline colours so the banner never stays blank/red due to cached CSS.
    const bg = bannerClass === 'net-negative' ? '#d83a3a' : '#0f8b66';
    headlineEl.style.setProperty('display', 'flex', 'important');
    headlineEl.style.setProperty('align-items', 'center', 'important');
    headlineEl.style.setProperty('justify-content', 'center', 'important');
    headlineEl.style.setProperty('width', '100%', 'important');
    headlineEl.style.setProperty('min-height', '46px', 'important');
    headlineEl.style.setProperty('background', bg, 'important');
    headlineEl.style.setProperty('color', '#ffffff', 'important');
    headlineEl.style.setProperty('border-radius', '14px', 'important');
    headlineEl.style.setProperty('padding', '10px 12px', 'important');
    headlineEl.style.setProperty('overflow', 'visible', 'important');
    headlineEl.style.setProperty('white-space', 'normal', 'important');
  }

  function renderFiiDii(data) {
    const rows = Array.isArray(data.categories) ? data.categories : [];
    if (headlineEl) {
      const headlineText = `${data.date || 'Latest'}: ${data.headline || 'FII / DII Activity'}`;
      headlineEl.innerHTML = `<span class="fii-headline-text">${headlineText}</span>`;
      applyHeadlineColour(headlineNetClass(data, rows));
    }
    if (tbody) {
      tbody.innerHTML = rows.map(row => `
        <tr>
          <td>${row.category || '-'}</td>
          <td>${fmtCr(row.buyValue)}</td>
          <td>${fmtCr(row.sellValue)}</td>
          <td class="net-value ${netClass(row.netValue)}">${fmtNet(row.netValue)}</td>
        </tr>`).join('') || '<tr><td colspan="4">Market flow data unavailable.</td></tr>';
    }
    if (updatedEl) {
      updatedEl.textContent = data.updatedAt ? `Updated: ${data.updatedAt}` : 'Values may be delayed.';
    }
  }

  const cacheSafeJsonUrl = jsonUrl + (jsonUrl.includes('?') ? '&' : '?') + 'v=' + Date.now();

  fetch(cacheSafeJsonUrl, { cache: 'no-store' })
    .then(res => {
      if (!res.ok) throw new Error('FII/DII JSON not found');
      return res.json();
    })
    .then(renderFiiDii)
    .catch(() => {
      if (headlineEl) { headlineEl.textContent = 'FII / DII Activity unavailable'; applyHeadlineColour('net-positive'); }
      if (updatedEl) updatedEl.textContent = 'Market flow data could not be loaded.';
    });
})();

// JSON-powered 52-week high-low market tools
(function () {
  const table = document.querySelector('table[data-market-json]');
  if (!table) return;

  const tbody = document.getElementById('marketTableBody') || table.querySelector('tbody');
  const updatedEl = document.getElementById('marketUpdated');
  const searchInput = document.getElementById('marketSearch');
  const sortDownBtn = document.getElementById('sortDownFromHigh');
  const sortLowBtn = document.getElementById('sortNearLow');
  const jsonUrl = table.getAttribute('data-market-json');
  let rows = [];
  let currentRows = [];

  function fmtNumber(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return '-';
    return num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  function fmtPct(value, showPlus) {
    const num = Number(value);
    if (!Number.isFinite(num)) return '-';
    const sign = showPlus && num > 0 ? '+' : '';
    return sign + num.toFixed(2) + '%';
  }
  function cls(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return '';
    return num >= 0 ? 'positive' : 'negative';
  }

  function isValidMarketRow(row) {
    const name = String(row.stockName || '').toLowerCase();
    const symbol = String(row.symbol || '').toLowerCase();
    const status = String(row.status || '').toLowerCase();
    const cmp = Number(row.cmp);
    const high52 = Number(row.high52);
    const low52 = Number(row.low52);

    if (name.includes('dummy') || symbol.includes('dummy')) return false;
    if (!Number.isFinite(cmp) || cmp <= 0) return false;
    if (!Number.isFinite(high52) || high52 <= 0) return false;
    if (!Number.isFinite(low52) || low52 <= 0) return false;
    if (status.includes('data unavailable') || status === 'unavailable') return false;

    return true;
  }
  function render(dataRows) {
    currentRows = dataRows;
    if (!dataRows.length) {
      tbody.innerHTML = '<tr><td colspan="8">No matching stocks found.</td></tr>';
      return;
    }
    tbody.innerHTML = dataRows.map(row => `
      <tr>
        <td>${row.stockName || '-'}</td>
        <td>${fmtNumber(row.high52)}</td>
        <td>${fmtNumber(row.low52)}</td>
        <td><strong>${fmtNumber(row.cmp)}</strong></td>
        <td class="${cls(row.downFromHighPct)}">${fmtPct(row.downFromHighPct)}</td>
        <td class="${cls(row.changePct)}">${fmtPct(row.changePct, true)}</td>
        <td class="${cls(row.aboveLowPct)}">${fmtPct(row.aboveLowPct, true)}</td>
        <td>${row.status || '-'}</td>
      </tr>`).join('');
  }

  function numericRows(sourceRows, key) {
    return sourceRows.filter(row => Number.isFinite(Number(row[key])) && Number.isFinite(Number(row.cmp)) && Number(row.cmp) > 0);
  }

  function stockLabel(row) {
    return `${row.stockName || row.symbol || '-'}`;
  }

  function miniList(items, valueKey, valueType) {
    if (!items.length) return '<li><span>No valid data</span><strong>-</strong></li>';
    return items.map(row => {
      const value = valueType === 'price' ? fmtNumber(row[valueKey]) : fmtPct(row[valueKey], valueKey !== 'downFromHighPct');
      const valueClass = valueType === 'price' ? '' : cls(row[valueKey]);
      return `<li><span>${stockLabel(row)}</span><strong class="${valueClass}">${value}</strong></li>`;
    }).join('');
  }

  function renderTopFiveBlocks(sourceRows) {
    const tableSection = table.closest('.market-table-section');
    if (!tableSection || !sourceRows.length) return;

    let summaryWrap = document.getElementById('marketTop5Grid') || tableSection.querySelector('.market-top5-grid');
    if (!summaryWrap) {
      summaryWrap = document.createElement('div');
      summaryWrap.className = 'market-top5-grid';
      const toolbar = tableSection.querySelector('.market-json-toolbar');
      if (toolbar) {
        tableSection.insertBefore(summaryWrap, toolbar);
      } else {
        tableSection.insertBefore(summaryWrap, tableSection.querySelector('.market-data-table-wrap'));
      }
    }

    const corrected = numericRows(sourceRows, 'downFromHighPct')
      .slice()
      .sort((a, b) => Number(a.downFromHighPct) - Number(b.downFromHighPct))
      .slice(0, 5);

    const nearLow = numericRows(sourceRows, 'aboveLowPct')
      .slice()
      .sort((a, b) => Number(a.aboveLowPct) - Number(b.aboveLowPct))
      .slice(0, 5);

    const strongest = numericRows(sourceRows, 'downFromHighPct')
      .slice()
      .sort((a, b) => Number(b.downFromHighPct) - Number(a.downFromHighPct))
      .slice(0, 5);

    const movers = numericRows(sourceRows, 'changePct')
      .slice()
      .sort((a, b) => Number(b.changePct) - Number(a.changePct))
      .slice(0, 5);

    summaryWrap.innerHTML = `
      <article class="market-top5-card">
        <p>Top 5 Most Corrected Stocks</p>
        <ul>${miniList(corrected, 'downFromHighPct', 'percent')}</ul>
      </article>
      <article class="market-top5-card">
        <p>Top 5 Stocks Near 52W Low</p>
        <ul>${miniList(nearLow, 'aboveLowPct', 'percent')}</ul>
      </article>
      <article class="market-top5-card">
        <p>Top 5 Strongest Stocks in Sector</p>
        <ul>${miniList(strongest, 'downFromHighPct', 'percent')}</ul>
      </article>
      <article class="market-top5-card">
        <p>Top 5 Positive Movers Today</p>
        <ul>${miniList(movers, 'changePct', 'percent')}</ul>
      </article>
    `;
  }
  function applySearch() {
    const q = (searchInput?.value || '').trim().toLowerCase();
    if (!q) return render(rows);
    render(rows.filter(row => String(row.symbol || '').toLowerCase().includes(q) || String(row.stockName || '').toLowerCase().includes(q)));
  }
  const cacheSafeJsonUrl = jsonUrl + (jsonUrl.includes('?') ? '&' : '?') + 'v=' + Date.now();

  fetch(cacheSafeJsonUrl, { cache: 'no-store' })
    .then(res => {
      if (!res.ok) throw new Error('JSON not found');
      return res.json();
    })
    .then(data => {
      rows = Array.isArray(data.stocks) ? data.stocks.filter(isValidMarketRow).slice() : [];
      if (updatedEl) updatedEl.textContent = data.updatedAt || data.sourceNote || 'JSON snapshot loaded';
      renderTopFiveBlocks(rows);
      render(rows);
    })
    .catch(() => {
      if (updatedEl) updatedEl.textContent = 'JSON data could not be loaded. Check the market-data JSON path.';
      tbody.innerHTML = '<tr><td colspan="8">Unable to load JSON data.</td></tr>';
    });
  searchInput?.addEventListener('input', applySearch);
  sortDownBtn?.addEventListener('click', () => { rows.sort((a,b) => Number(a.downFromHighPct) - Number(b.downFromHighPct)); applySearch(); });
  sortLowBtn?.addEventListener('click', () => { rows.sort((a,b) => Number(a.aboveLowPct) - Number(b.aboveLowPct)); applySearch(); });
})();


// Tool-wise Razorpay payment integration for Automation In Trade
(function () {
  const PAYMENT_CONFIG = {
    key: 'rzp_live_T0ioyzNwAjzzFA',
    businessName: 'Automation In Trade',
    websiteUrl: 'https://automationintrade.com/',
    whatsappNumber: '918197565002',
    defaultTrialAmount: 499,
    defaultPurchaseAmount: 9999,
    testAmount: 1,
    apiBaseUrl: window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
      ? 'https://automationintrade.com/api/razorpay'
      : '/api/razorpay'
  };

  const TOOL_NAMES = {
    'result-scanner': 'Result Scanner',
    'overall-result-score': 'Overall Result Score',
    'result-decision-map': 'Result Decision Map',
    'result-impact-card-generator': 'Result Impact Card Generator',
    'news-card': 'News Card',
    'institutional-holding-activity-tracker': 'Institutional Holding Activity Tracker',
    'technical-zone-finder': 'Technical Zone Finder',
    'option-chain-sentiment-dashboard': 'Option Chain Sentiment Dashboard',
    'sector-buying-flow-tracker': 'Sector Buying Flow Tracker',
    'fii-dii-flow-visualizer': 'FII/DII Flow Visualizer',
    'portfolio-analyzer': 'Portfolio Analyzer',
    'ait-smart-move-indicator': 'AIT Smart Move Indicator',
    'price-action-zone-finder': 'Price Action Zone Finder',
    '52w-high-low-scanner': '52W High-Low Scanner',
    'tool-test': 'Automation In Trade Payment Test'
  };

  const TOOL_PRICING = {
    'News Card': { trial: 499, full: 2999 },
    'Result Impact Card Generator': { trial: 499, full: 4999 },
    'FII/DII Flow Visualizer': { trial: 499, full: 4999 },
    'Overall Result Score': { trial: 499, full: 4999 },
    'Result Decision Map': { trial: 499, full: 4999 },
    'Result Scanner': { trial: 499, full: 4999 },
    '52W High-Low Scanner': { trial: 499, full: 4999 },
    'Sector Buying Flow Tracker': { trial: 499, full: 7999 },
    'Technical Zone Finder': { trial: 499, full: 7999 },
    'Institutional Holding Activity Tracker': { trial: 999, full: 9999 },
    'Option Chain Sentiment Dashboard': { trial: 999, full: 9999 },
    'Portfolio Analyzer': { trial: 999, full: 9999 },
    'AIT Smart Move Indicator': { trial: 999, full: 9999 },
    'Price Action Zone Finder': { trial: 999, full: 9999 },
    'Stock Research Premium': { trial: 499, full: 9999 },
    'Automation In Trade Payment Test': { trial: 1, full: 1 }
  };

  function getToolPricing(tool) {
    return TOOL_PRICING[tool] || {
      trial: PAYMENT_CONFIG.defaultTrialAmount,
      full: PAYMENT_CONFIG.defaultPurchaseAmount
    };
  }

  function rupee(amount) {
    return '₹' + Number(amount).toLocaleString('en-IN');
  }

  function getPageTool() {
    const path = window.location.pathname.toLowerCase();
    const parts = path.split('/').filter(Boolean);
    const slug = parts[parts.length - 1] || 'automation-in-trade';
    if (slug === 'tool-test') return TOOL_NAMES['tool-test'];
    if (TOOL_NAMES[slug]) return TOOL_NAMES[slug];
    if (path.includes('/market-tools/')) return TOOL_NAMES['52w-high-low-scanner'];
    return 'Automation In Trade Tool';
  }

  function ensureRazorpayLoaded() {
    return new Promise((resolve, reject) => {
      if (window.Razorpay) return resolve();
      const existing = document.querySelector('script[data-razorpay-checkout]');
      if (existing) {
        existing.addEventListener('load', resolve, { once: true });
        existing.addEventListener('error', reject, { once: true });
        return;
      }
      const s = document.createElement('script');
      s.src = 'https://checkout.razorpay.com/v1/checkout.js';
      s.async = true;
      s.dataset.razorpayCheckout = 'true';
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }

  function paymentSuccessMessage(tool, plan, amount, paymentId) {
    return encodeURIComponent(`Payment successful for ${tool} - ${plan} (${rupee(amount)}). Payment ID: ${paymentId}. Please activate my access. Website: ${PAYMENT_CONFIG.websiteUrl}`);
  }

  function buildSuccessUrl(tool, plan, amount, paymentId, orderId, captureStatus) {
    const url = new URL('/payment-success/', window.location.origin);
    url.searchParams.set('tool', tool);
    url.searchParams.set('plan', plan);
    url.searchParams.set('amount', String(amount));
    url.searchParams.set('payment_id', paymentId || 'N/A');
    url.searchParams.set('order_id', orderId || 'N/A');
    url.searchParams.set('capture_status', captureStatus || 'verified');
    url.searchParams.set('status', 'success');
    return url.toString();
  }

  async function apiPost(path, payload) {
    const response = await fetch(`${PAYMENT_CONFIG.apiBaseUrl}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    let data = {};
    try { data = await response.json(); } catch (error) {}
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || 'Payment server request failed.');
    }
    return data;
  }

  async function createRazorpayOrder(tool, plan, amount) {
    return apiPost('/order', {
      tool,
      plan,
      amount,
      website: PAYMENT_CONFIG.websiteUrl
    });
  }

  async function verifyAndCapturePayment(payload) {
    return apiPost('/verify', payload);
  }

  function showPaymentStatus(type, title, message, whatsappUrl) {
    let box = document.querySelector('.payment-status-box');
    if (!box) {
      box = document.createElement('div');
      box.className = 'payment-status-box';
      document.body.appendChild(box);
    }
    box.className = `payment-status-box ${type}`;
    box.innerHTML = `<button class="payment-status-close" type="button" aria-label="Close payment message">×</button><strong>${title}</strong><p>${message}</p>${whatsappUrl ? `<a class="btn btn-primary" href="${whatsappUrl}" target="_blank" rel="noopener">Send WhatsApp Confirmation</a>` : ''}`;
    box.querySelector('.payment-status-close').addEventListener('click', () => box.remove());
    window.setTimeout(() => { if (document.body.contains(box)) box.remove(); }, 16000);
  }

  async function openPayment(tool, plan, amount) {
    try {
      await ensureRazorpayLoaded();
    } catch (error) {
      showPaymentStatus('error', 'Payment could not start', 'Razorpay checkout script did not load. Please refresh and try again.', null);
      return;
    }

    let orderData;
    try {
      showPaymentStatus('muted', 'Starting secure payment', 'Creating a Razorpay order. Please wait...', null);
      orderData = await createRazorpayOrder(tool, plan, amount);
    } catch (error) {
      showPaymentStatus('error', 'Payment could not start', `${error.message} Please deploy the Razorpay Worker/API first, then try again.`, null);
      return;
    }

    const orderId = orderData.order_id;
    if (!orderId) {
      showPaymentStatus('error', 'Payment could not start', 'Razorpay Order ID was not created. Please check the backend API.', null);
      return;
    }

    const options = {
      key: PAYMENT_CONFIG.key,
      amount: amount * 100,
      currency: 'INR',
      name: PAYMENT_CONFIG.businessName,
      description: `${tool} - ${plan}`,
      image: `${PAYMENT_CONFIG.websiteUrl}logo.png`,
      order_id: orderId,
      notes: {
        tool_name: tool,
        plan_name: plan,
        website: PAYMENT_CONFIG.websiteUrl,
        whatsapp: PAYMENT_CONFIG.whatsappNumber
      },
      theme: { color: '#0f766e' },
      handler: async function (response) {
        const paymentId = response.razorpay_payment_id || 'N/A';
        try {
          showPaymentStatus('muted', 'Verifying payment', 'Please wait while we verify and capture the payment securely...', null);
          const verified = await verifyAndCapturePayment({
            tool,
            plan,
            amount,
            razorpay_order_id: response.razorpay_order_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature
          });
          window.location.href = buildSuccessUrl(tool, plan, amount, paymentId, response.razorpay_order_id, verified.capture_status || verified.payment_status || 'captured');
        } catch (error) {
          showPaymentStatus('error', 'Payment verification failed', `${error.message} Please contact support with Payment ID: ${paymentId}.`, null);
        }
      },
      modal: {
        ondismiss: function () {
          showPaymentStatus('muted', 'Payment closed', 'No payment was completed. You can try again anytime.', null);
        }
      }
    };

    const rzp = new window.Razorpay(options);
    rzp.on('payment.failed', function (response) {
      const reason = response && response.error && response.error.description ? response.error.description : 'Payment failed or was cancelled.';
      showPaymentStatus('error', 'Payment failed', reason, null);
    });
    rzp.open();
  }

  function paymentButtonsHtml(tool, compact) {
    const pricing = getToolPricing(tool);
    return `<div class="tool-pricing-actions${compact ? ' compact' : ''}" data-tool-name="${tool}">
      <button type="button" class="tool-price-btn trial" data-plan="Trial Access" data-amount="${pricing.trial}" data-tool="${tool}">Start Trial ${rupee(pricing.trial)}</button>
      <button type="button" class="tool-price-btn full" data-plan="Full Access" data-amount="${pricing.full}" data-tool="${tool}">Get Full Access ${rupee(pricing.full)}</button>
    </div>`;
  }

  function enhanceToolCards() {
    document.querySelectorAll('.tool-card').forEach(card => {
      if (card.querySelector('.tool-pricing-actions')) return;
      const title = card.querySelector('h3') ? card.querySelector('h3').textContent.trim() : '';
      if (!title) return;
      card.insertAdjacentHTML('beforeend', paymentButtonsHtml(title, true));
    });
  }

  function replaceRequestButtons() {
    const tool = getPageTool();
    document.querySelectorAll('a').forEach(anchor => {
      const text = anchor.textContent.trim().toLowerCase();
      const href = anchor.getAttribute('href') || '';
      if ((text.includes('request trial') || text.includes('purchase access')) && href.includes('docs.google.com/forms')) {
        const wrapper = document.createElement('div');
        wrapper.className = 'inline-tool-pricing';
        wrapper.innerHTML = paymentButtonsHtml(tool, false);
        anchor.replaceWith(wrapper);
      }
    });
  }

  function attachPaymentEvents() {
    document.addEventListener('click', function (event) {
      const btn = event.target.closest('.tool-price-btn');
      if (!btn) return;
      event.preventDefault();
      event.stopPropagation();
      const tool = btn.dataset.tool || getPageTool();
      const plan = btn.dataset.plan || 'Tool Access';
      const amount = Number(btn.dataset.amount || PAYMENT_CONFIG.defaultPurchaseAmount);
      openPayment(tool, plan, amount);
    });
  }

  function initTestPage() {
    const testRoot = document.querySelector('[data-tool-test-payment]');
    if (!testRoot) return;
    const tool = TOOL_NAMES['tool-test'];
    testRoot.innerHTML = `<div class="test-payment-card"><p class="eyebrow">Payment Test</p><h1>Test Razorpay Payment</h1><p>Use this page only to test whether the Razorpay checkout, success page, WhatsApp confirmation, and auto-home redirect flow are working properly.</p><div class="tool-pricing-actions"><button type="button" class="tool-price-btn trial" data-plan="Test Payment" data-amount="${PAYMENT_CONFIG.testAmount}" data-tool="${tool}">Pay ₹1 Test Payment</button></div><p class="payment-note">After successful payment, you will be redirected to the payment success page.</p></div>`;
  }

  function escapeHtml(value) {
    return String(value || '').replace(/[&<>'"]/g, function (char) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char];
    });
  }

  function initPaymentSuccessPage() {
    const root = document.querySelector('[data-payment-success-page]');
    if (!root) return;

    const params = new URLSearchParams(window.location.search);
    const tool = params.get('tool') || 'Automation In Trade Tool';
    const plan = params.get('plan') || 'Tool Access';
    const amount = Number(params.get('amount') || 0);
    const paymentId = params.get('payment_id') || 'N/A';
    const orderId = params.get('order_id') || 'N/A';
    const captureStatus = params.get('capture_status') || 'verified';
    const whatsappUrl = `https://wa.me/${PAYMENT_CONFIG.whatsappNumber}?text=${paymentSuccessMessage(tool, plan, amount, paymentId)}`;

    root.innerHTML = `<div class="payment-success-card">
      <div class="success-icon" aria-hidden="true">✓</div>
      <p class="eyebrow">Payment Successful</p>
      <h1>Thank you for your payment</h1>
      <p class="success-summary">Your payment for <strong>${escapeHtml(tool)} - ${escapeHtml(plan)}</strong> has been received.</p>
      <div class="payment-success-details">
        <div><span>Amount</span><strong>${rupee(amount)}</strong></div>
        <div><span>Payment ID</span><strong>${escapeHtml(paymentId)}</strong></div>
        <div><span>Order ID</span><strong>${escapeHtml(orderId)}</strong></div>
        <div><span>Status</span><strong>${escapeHtml(captureStatus)}</strong></div>
      </div>
      <p class="success-instruction">Please send the WhatsApp confirmation to activate your access.</p>
      <div class="success-actions">
        <a class="btn btn-primary" href="${whatsappUrl}" target="_blank" rel="noopener" id="paymentSuccessWhatsappBtn">Send WhatsApp Confirmation</a>
        <a class="btn btn-secondary" href="/">Go to Home</a>
      </div>
      <p class="redirect-note">You will be redirected to home in <span id="paymentRedirectSeconds">12</span> seconds.</p>
    </div>`;

    let seconds = 12;
    const secondsEl = document.getElementById('paymentRedirectSeconds');
    const tick = window.setInterval(function () {
      seconds -= 1;
      if (secondsEl) secondsEl.textContent = String(seconds);
      if (seconds <= 0) {
        window.clearInterval(tick);
        window.location.href = '/';
      }
    }, 1000);

    const whatsappBtn = document.getElementById('paymentSuccessWhatsappBtn');
    if (whatsappBtn) {
      whatsappBtn.addEventListener('click', function () {
        if (seconds > 6) seconds = 6;
      });
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    enhanceToolCards();
    replaceRequestButtons();
    initTestPage();
    initPaymentSuccessPage();
    attachPaymentEvents();
  });
})();


// V106: Homepage stock research search using lightweight JSON + HTML cards.
(function initStockResearchSearch() {
  const card = document.getElementById('stockResearchResult');
  const form = document.getElementById('stockResearchForm');
  const input = document.getElementById('stockSearchInput');
  const select = document.getElementById('researchTypeSelect');
  const datalist = document.getElementById('stockResearchSuggestions');
  if (!card || !form || !input || !select) return;

  const jsonUrl = card.getAttribute('data-stock-research-json') || '/market-data/stock-research-index.json';
  let stocks = [];
  let updatedAt = '';

  const toolMap = {
    'price-action': { key: 'priceAction', label: 'Price Action', page: '/price-action-zone-finder/', badge: 'Setup View' },
    'results': { key: 'results', label: 'Results', page: '/result-scanner/', badge: 'Result Quality' },
    'technical-analysis': { key: 'technicalAnalysis', label: 'Technical Analysis', page: '/technical-zone-finder/', badge: 'Technical View' }
  };

  const FREE_RESEARCH_INDICES = new Set(['NIFTY 50', 'NIFTY BANK', 'BANK NIFTY']);
  const PREMIUM_RESEARCH_TOOL = 'Stock Research Premium';
  const PREMIUM_TRIAL_AMOUNT = 499;
  const PREMIUM_FULL_AMOUNT = 9999;

  function rupeeLocal(amount) {
    return '₹' + Number(amount).toLocaleString('en-IN');
  }

  function isFreeResearchStock(stock) {
    if (!stock) return false;
    if (stock.accessTier === 'free' || stock.isFree === true) return true;
    if (stock.accessTier === 'premium' || stock.isFree === false) return false;
    const indices = Array.isArray(stock.indices) ? stock.indices : [];
    return indices.some(indexName => FREE_RESEARCH_INDICES.has(normalize(indexName)));
  }

  function normalize(value) {
    return String(value || '').trim().toUpperCase().replace(/\s+/g, ' ');
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function formatNumber(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return '—';
    return num.toLocaleString('en-IN', { maximumFractionDigits: 2, minimumFractionDigits: 2 });
  }

  function formatPct(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return '—';
    const sign = num > 0 ? '+' : '';
    return `${sign}${num.toFixed(2)}%`;
  }

  function oneDayMoveClass(value) {
    const num = Number(value);
    if (!Number.isFinite(num) || num === 0) return 'is-neutral';
    return num > 0 ? 'is-positive' : 'is-negative';
  }

  function formatSigned(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return '—';
    const sign = num > 0 ? '+' : '';
    return `${sign}${num.toFixed(2)}`;
  }

  function toneClass(value) {
    const text = normalize(value);
    const num = Number(value);
    if (Number.isFinite(num)) return num >= 0 ? 'is-positive' : 'is-negative';
    if (/STRONG|UPTREND|BULL|GOOD|EXCELLENT|POSITIVE|BUY|IMPROV/.test(text)) return 'is-positive';
    if (/WEAK|DOWNTREND|BEAR|POOR|NEGATIVE|SELL|AVOID|RISK|CAUTION/.test(text)) return 'is-negative';
    return 'is-neutral';
  }

  function displayValue(value, type) {
    if (value === null || value === undefined || value === '') return '—';
    if (type === 'price') return formatNumber(value);
    if (type === 'percent') return formatPct(value);
    if (type === 'signed') return formatSigned(value);
    return escapeHtml(value);
  }

  function toPlainText(value) {
    return String(value ?? '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
  }

  function truncateMeta(value, limit) {
    const text = toPlainText(value);
    if (text.length <= limit) return text;
    return text.slice(0, limit - 1).replace(/\s+\S*$/, '') + '…';
  }

  function setOrCreateMeta(attrName, attrValue, content) {
    let tag = document.head.querySelector(`meta[${attrName}="${attrValue}"]`);
    if (!tag) {
      tag = document.createElement('meta');
      tag.setAttribute(attrName, attrValue);
      document.head.appendChild(tag);
    }
    tag.setAttribute('content', content);
  }

  function updateResearchSeoDescription(stock, tool, info, data) {
    if (!stock || !tool) return;
    const summary = toPlainText((data && data.summary) || (info && info.summary) || `${tool.label} research card with price, trend, result and market data.`);
    const metaText = truncateMeta(`${stock.symbol} ${stock.stockName || ''} ${tool.label}: ${summary} CMP ${formatNumber(stock.cmp)}, 1D ${formatPct(stock.changePct)}.`, 165);
    setOrCreateMeta('name', 'description', metaText);
    setOrCreateMeta('property', 'og:description', metaText);
    setOrCreateMeta('name', 'twitter:description', metaText);
    if (stock.symbol) document.title = `${stock.symbol} ${tool.label} | Automation In Trade`;
  }

  function findStock(query) {
    const q = normalize(query).replace(/\s+\|.*$/, '');
    if (!q) return null;
    return stocks.find(stock => normalize(stock.symbol) === q) ||
      stocks.find(stock => normalize(`${stock.symbol} | ${stock.stockName}`) === normalize(query)) ||
      stocks.find(stock => normalize(stock.stockName) === q) ||
      stocks.find(stock => normalize(stock.symbol).includes(q) || normalize(stock.stockName).includes(q));
  }

  function findExactStock(query) {
    const q = normalize(query).replace(/\s+\|.*$/, '');
    if (!q) return null;
    return stocks.find(stock => normalize(stock.symbol) === q) ||
      stocks.find(stock => normalize(`${stock.symbol} | ${stock.stockName}`) === normalize(query)) ||
      stocks.find(stock => normalize(stock.stockName) === q);
  }

  function getToolData(stock, tool) {
    const info = stock[tool.key] || {};
    return info.data || info.htmlData || null;
  }

  function kv(label, value, tone, type) {
    return `<div class="research-kv"><span>${escapeHtml(label)}</span><strong class="${tone || toneClass(value)}">${displayValue(value, type)}</strong></div>`;
  }

  function metric(label, value, tone, type) {
    return `<div class="research-metric"><span>${escapeHtml(label)}</span><strong class="${tone || toneClass(value)}">${displayValue(value, type)}</strong></div>`;
  }

  function renderRows(rows) {
    if (!Array.isArray(rows) || !rows.length) return '';
    return `<div class="research-table-like">${rows.map(row => `
      <div class="research-row">
        <span>${escapeHtml(row.label || row.name || '')}</span>
        <strong class="${toneClass(row.tone || row.value)}">${displayValue(row.value, row.type)}</strong>
      </div>`).join('')}</div>`;
  }

  function buildFallbackData(stock, toolId) {
    const base = {
      view: 'Data Ready',
      summary: 'This stock is available in the search index. Add detailed JSON values to show a complete HTML scorecard.',
      metrics: [
        { label: 'CMP', value: stock.cmp, type: 'price' },
        { label: '1D Change', value: stock.changePct, type: 'percent', tone: oneDayMoveClass(stock.changePct) },
        { label: 'Updated', value: stock.updatedAt || updatedAt || 'Latest' }
      ],
      rows: [
        { label: 'Output Format', value: 'HTML JSON Card' },
        { label: 'Image Dependency', value: 'Not Required' },
        { label: 'Next Step', value: 'Add detailed JSON' }
      ]
    };
    if (toolId === 'price-action') base.view = 'Price Action View';
    if (toolId === 'results') base.view = 'Result Quality View';
    if (toolId === 'technical-analysis') base.view = 'Technical View';
    return base;
  }

  function renderHtmlResearchCard(stock, tool, info) {
    const data = getToolData(stock, tool) || buildFallbackData(stock, select.value);
    const metrics = Array.isArray(data.metrics) ? data.metrics : [];
    const rows = Array.isArray(data.rows) ? data.rows : [];
    const levels = Array.isArray(data.levels) ? data.levels : [];
    const note = data.note || info.note || '';
    const view = data.view || data.signal || data.grade || tool.badge;

    if (select.value === 'results') {
      return `
        <article class="research-html-card results-html-card">
          <div class="research-card-head">
            <span>${escapeHtml(tool.label)}</span>
            <strong class="${toneClass(view)}">${escapeHtml(view)}</strong>
          </div>
          <div class="research-score-band ${toneClass(data.score || view)}">
            <div><span>Result Score</span><strong>${data.score ?? '—'}</strong></div>
            <div><span>Grade</span><strong>${escapeHtml(data.grade || view)}</strong></div>
            <div><span>Confidence</span><strong>${displayValue(data.confidence, 'percent')}</strong></div>
          </div>
          <div class="research-metrics-grid">
            ${metrics.map(item => metric(item.label, item.value, item.tone ? toneClass(item.tone) : '', item.type)).join('')}
          </div>
          ${renderRows(rows)}
        </article>`;
    }

    return `
      <article class="research-html-card">
        <div class="research-card-head">
          <span>${escapeHtml(tool.label)}</span>
          <strong class="${toneClass(view)}">${escapeHtml(view)}</strong>
        </div>
        <div class="research-metrics-grid">
          ${metrics.map(item => metric(item.label, item.value, item.tone ? toneClass(item.tone) : '', item.type)).join('')}
        </div>
        ${levels.length ? `<div class="research-levels">${levels.map(item => kv(item.label, item.value, item.tone ? toneClass(item.tone) : '', item.type)).join('')}</div>` : ''}
        ${renderRows(rows)}
      </article>`;
  }

  function renderPremiumResult(stock, tool) {
    const stockTitle = `${stock.symbol}${stock.stockName ? ' | ' + stock.stockName : ''}`;
    updateResearchSeoDescription(stock, tool, stock[tool.key] || {}, null);
    card.innerHTML = `
      <div class="stock-result-loaded stock-result-premium-locked">
        <article class="premium-lock-card">
          <span class="premium-lock-badge">🔒 Premium</span>
          <h2>${escapeHtml(stock.symbol)}</h2>
          <h3>${escapeHtml(stock.stockName || '')}</h3>
          <p>${escapeHtml(tool.label)} for this stock is part of Premium Research Tools. Free access is available for NIFTY 50 and Bank Nifty stocks.</p>
          <div class="premium-feature-list">
            <span>Price Action</span>
            <span>Results</span>
            <span>Technical Analysis</span>
          </div>
          <div class="premium-cta-box">
            <strong>Unlock Premium Research</strong>
            <p>Get access to locked stock research cards through the paid tool flow.</p>
            <div class="premium-cta-actions">
              <button type="button" class="tool-price-btn trial" data-plan="Premium Trial Access" data-amount="${PREMIUM_TRIAL_AMOUNT}" data-tool="${PREMIUM_RESEARCH_TOOL}">Start Trial ${rupeeLocal(PREMIUM_TRIAL_AMOUNT)}</button>
              <button type="button" class="tool-price-btn full" data-plan="Premium Full Access" data-amount="${PREMIUM_FULL_AMOUNT}" data-tool="${PREMIUM_RESEARCH_TOOL}">Unlock ${rupeeLocal(PREMIUM_FULL_AMOUNT)}</button>
            </div>
          </div>
        </article>
      </div>`;
  }

  function renderResult(stock) {
    if (!stock) {
      card.innerHTML = `<div class="stock-result-empty"><span class="stock-result-badge">No match found</span><h2>Search another stock symbol.</h2><p>Try exact NSE symbols like RELIANCE, TCS, INFY, AXISBANK or M&amp;M.</p></div>`;
      return;
    }

    const tool = toolMap[select.value] || toolMap['price-action'];
    if (!isFreeResearchStock(stock)) {
      renderPremiumResult(stock, tool);
      return;
    }

    const info = stock[tool.key] || {};
    const data = getToolData(stock, tool);
    updateResearchSeoDescription(stock, tool, info, data);
    const indices = Array.isArray(stock.indices) && stock.indices.length ? stock.indices.slice(0, 3).join(', ') : 'Stock universe';

    card.innerHTML = `
      <div class="stock-result-loaded stock-result-two-boxes stock-result-html-mode">
        <aside class="stock-result-info-box">
          <span class="stock-result-badge">${tool.label}</span>
          <h2>${escapeHtml(stock.symbol)}</h2>
          <h3>${escapeHtml(stock.stockName || '')}</h3>
          <div class="stock-result-meta compact-meta">
            <span>CMP: ${formatNumber(stock.cmp)}</span>
            <span>1D: <strong class="stock-one-day-value ${oneDayMoveClass(stock.changePct)}">${formatPct(stock.changePct)}</strong></span>
            <span>${escapeHtml(indices)}</span>
            <span>Updated: ${escapeHtml(updatedAt || stock.updatedAt || 'Latest')}</span>
          </div>
          <div class="stock-result-actions">
            <a href="${tool.page}">Open ${tool.label} Tool</a>
          </div>
        </aside>
        <section class="stock-result-image-box stock-result-html-box">
          ${renderHtmlResearchCard(stock, tool, info)}
        </section>
      </div>`;
  }

  const suggestionListId = datalist ? datalist.id : '';
  const MAX_SUGGESTIONS = 12;

  function escapeAttr(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function clearSuggestions() {
    if (datalist) datalist.innerHTML = '';
    input.removeAttribute('list');
  }

  function populateDatalist(query) {
    if (!datalist) return;
    const q = normalize(query);
    if (!q) {
      clearSuggestions();
      return;
    }

    const matches = stocks
      .map(stock => {
        const symbol = normalize(stock.symbol);
        const name = normalize(stock.stockName);
        const starts = symbol.startsWith(q) || name.startsWith(q);
        const contains = symbol.includes(q) || name.includes(q);
        return { stock, score: starts ? 0 : contains ? 1 : 9 };
      })
      .filter(item => item.score < 9)
      .sort((a, b) => a.score - b.score || normalize(a.stock.symbol).localeCompare(normalize(b.stock.symbol)))
      .slice(0, MAX_SUGGESTIONS)
      .map(item => {
        const label = `${item.stock.symbol} | ${item.stock.stockName || item.stock.symbol}${isFreeResearchStock(item.stock) ? '' : ' 🔒 Premium'}`;
        return `<option value="${escapeAttr(label)}"></option>`;
      })
      .join('');

    datalist.innerHTML = matches;
    if (matches && suggestionListId) {
      input.setAttribute('list', suggestionListId);
    } else {
      input.removeAttribute('list');
    }
  }

  fetch(jsonUrl + (jsonUrl.includes('?') ? '&' : '?') + 'v=' + Date.now(), { cache: 'no-store' })
    .then(res => {
      if (!res.ok) throw new Error('Stock research index not found');
      return res.json();
    })
    .then(data => {
      stocks = Array.isArray(data.stocks) ? data.stocks : [];
      updatedAt = data.updatedAt || '';
      clearSuggestions();
      const researchFromUrl = new URLSearchParams(window.location.search);
      const stockFromUrl = researchFromUrl.get('stock');
      const toolFromUrl = researchFromUrl.get('research') || researchFromUrl.get('tool');
      if (toolFromUrl && toolMap[toolFromUrl]) select.value = toolFromUrl;
      if (stockFromUrl) {
        input.value = stockFromUrl;
        const directStock = findStock(stockFromUrl);
        if (directStock) renderResult(directStock);
      }
    })
    .catch(() => {
      card.innerHTML = `<div class="stock-result-empty"><span class="stock-result-badge">JSON not loaded</span><h2>Stock search data is unavailable.</h2><p>Check /market-data/stock-research-index.json in your GitHub repo.</p></div>`;
    });

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    renderResult(findStock(input.value));
  });

  input.addEventListener('focus', () => {
    populateDatalist(input.value);
  });

  input.addEventListener('click', () => {
    if (!normalize(input.value)) clearSuggestions();
  });

  input.addEventListener('change', () => {
    const stock = findStock(input.value);
    if (stock) renderResult(stock);
  });

  let stockSearchTimer = null;
  input.addEventListener('input', () => {
    populateDatalist(input.value);
    window.clearTimeout(stockSearchTimer);
    stockSearchTimer = window.setTimeout(() => {
      const stock = findExactStock(input.value);
      if (stock) renderResult(stock);
    }, 180);
  });

  select.addEventListener('change', () => {
    const stock = findStock(input.value);
    if (stock) renderResult(stock);
  });

  document.querySelectorAll('[data-stock-pick]').forEach(button => {
    button.addEventListener('click', () => {
      const symbol = button.getAttribute('data-stock-pick') || '';
      const research = button.getAttribute('data-research-pick') || select.value;
      select.value = research;
      input.value = symbol;
      renderResult(findStock(symbol));
    });
  });
})();


/* AIT Ticket Form v136: auto email + centered success view */
(function(){
  const SUPPORT_EMAIL = 'automationintrade@gmail.com';
  const FORM_ENDPOINT = 'https://formsubmit.co/ajax/' + SUPPORT_EMAIL;

  function ticketId(){
    const d = new Date();
    const date = d.getFullYear().toString() + String(d.getMonth()+1).padStart(2,'0') + String(d.getDate()).padStart(2,'0');
    const rand = Math.random().toString(36).slice(2, 6).toUpperCase();
    return 'AIT-' + date + '-' + rand;
  }

  function esc(value){
    return String(value || '').replace(/[&<>"']/g, function(ch){
      return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]);
    });
  }

  function initTicketForms(){
    document.querySelectorAll('[data-ticket-form]').forEach(function(form){
      if(form.dataset.ready === '1') return;
      form.dataset.ready = '1';

      form.addEventListener('submit', async function(event){
        event.preventDefault();
        const data = new FormData(form);
        const id = ticketId();
        const name = data.get('name') || '';
        const email = data.get('email') || '';
        const phone = data.get('phone') || '';
        const category = data.get('category') || '';
        const page = data.get('page') || '';
        const priority = data.get('priority') || 'Normal';
        const message = data.get('message') || '';
        const subject = 'Automation In Trade Ticket ' + id + ' - ' + category;
        const output = form.querySelector('.ticket-output');
        const submit = form.querySelector('.ticket-submit');

        if(submit){
          submit.disabled = true;
          submit.textContent = 'Generating...';
        }
        if(output){
          output.innerHTML = '<div class="ticket-success ticket-success-loading"><strong>Generating ticket...</strong><span>Please wait while your ticket is being created.</span></div>';
        }

        const payload = new FormData();
        payload.append('_subject', subject);
        payload.append('_template', 'table');
        payload.append('_captcha', 'false');
        payload.append('Ticket ID', id);
        payload.append('Name', name);
        payload.append('Email', email);
        payload.append('WhatsApp', phone);
        payload.append('Category', category);
        payload.append('Related Tool / Page', page || '-');
        payload.append('Priority', priority);
        payload.append('Message', message);
        payload.append('Page URL', window.location.href);
        payload.append('Generated At', new Date().toLocaleString('en-IN'));

        let sent = false;
        try {
          const response = await fetch(FORM_ENDPOINT, {
            method: 'POST',
            headers: { 'Accept': 'application/json' },
            body: payload
          });
          sent = response.ok;
        } catch (err) {
          sent = false;
        }

        form.classList.add('ticket-submitted');
        if(output){
          output.innerHTML = '<div class="ticket-success ticket-success-final">' +
            '<strong>Ticket generated: ' + esc(id) + '</strong>' +
            '<span>' + (sent ? 'Your ticket details have been emailed to Automation In Trade support.' : 'Your ticket was generated. Email delivery may require one-time form activation, so please keep this ticket ID saved.') + '</span>' +
            '<div class="ticket-summary">' +
              '<p><b>Name:</b> ' + esc(name) + '</p>' +
              '<p><b>Email:</b> ' + esc(email) + '</p>' +
              '<p><b>WhatsApp:</b> ' + esc(phone) + '</p>' +
              '<p><b>Category:</b> ' + esc(category) + '</p>' +
              '<p><b>Priority:</b> ' + esc(priority) + '</p>' +
              (page ? '<p><b>Related Tool/Page:</b> ' + esc(page) + '</p>' : '') +
              '<p><b>Message:</b> ' + esc(message) + '</p>' +
            '</div>' +
          '</div>';

          setTimeout(function(){
            output.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }, 80);
        }
      });
    });
  }

  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initTicketForms);
  else initTicketForms();
})();

