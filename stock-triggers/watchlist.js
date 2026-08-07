(function () {
  'use strict';

  const STORAGE_KEY = 'aitStockTriggerWatchlistV1';
  const FREE_LIMIT = 5;

  function read() {
    try {
      const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || '[]');
      return Array.isArray(parsed)
        ? parsed.filter((item) => item && item.symbol).map((item) => ({
            symbol: String(item.symbol).trim().toUpperCase(),
            name: String(item.name || item.symbol).trim(),
            followedAt: item.followedAt || new Date().toISOString()
          }))
        : [];
    } catch (error) {
      return [];
    }
  }

  function write(items) {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
    } catch (error) {
      showToast('Watchlist could not be saved in this browser.', true);
    }
  }

  function getSymbols() {
    return read().map((item) => item.symbol);
  }

  function isFollowed(symbol) {
    const normalized = String(symbol || '').trim().toUpperCase();
    return read().some((item) => item.symbol === normalized);
  }

  function showToast(message, withUpgrade) {
    let toast = document.getElementById('aitWatchlistToast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'aitWatchlistToast';
      toast.className = 'ait-watchlist-toast';
      toast.setAttribute('role', 'status');
      toast.setAttribute('aria-live', 'polite');
      document.body.appendChild(toast);
    }
    toast.innerHTML = `<span>${escapeHtml(message)}</span>${withUpgrade ? '<a href="/contact/?topic=stock-trigger-pro">Request unlimited alerts</a>' : ''}`;
    toast.classList.add('is-visible');
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => toast.classList.remove('is-visible'), 4500);
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, (char) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[char]);
  }

  function refreshButtons() {
    const items = read();
    const symbols = new Set(items.map((item) => item.symbol));
    document.querySelectorAll('[data-ait-follow-symbol]').forEach((button) => {
      const symbol = String(button.dataset.aitFollowSymbol || '').trim().toUpperCase();
      const active = symbols.has(symbol);
      button.classList.toggle('is-following', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
      button.textContent = active ? `Following ${symbol}` : `Follow ${symbol}`;
    });
    document.querySelectorAll('[data-ait-watchlist-count]').forEach((node) => {
      node.textContent = String(items.length);
    });
  }

  function toggle(symbol, name) {
    const normalized = String(symbol || '').trim().toUpperCase();
    if (!normalized) return { changed: false, reason: 'missing-symbol' };
    const items = read();
    const index = items.findIndex((item) => item.symbol === normalized);
    let following = false;

    if (index >= 0) {
      items.splice(index, 1);
      showToast(`${normalized} removed from your browser watchlist.`, false);
    } else {
      if (items.length >= FREE_LIMIT) {
        showToast(`The free browser watchlist supports ${FREE_LIMIT} stocks.`, true);
        return { changed: false, reason: 'limit', items };
      }
      items.push({
        symbol: normalized,
        name: String(name || normalized).trim(),
        followedAt: new Date().toISOString()
      });
      following = true;
      showToast(`${normalized} added. Use “Watchlist only” on the trigger feed.`, false);
    }

    write(items);
    refreshButtons();
    window.dispatchEvent(new CustomEvent('ait:watchlist-changed', { detail: { items, symbol: normalized, following } }));
    return { changed: true, following, items };
  }

  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-ait-follow-symbol]');
    if (!button) return;
    event.preventDefault();
    toggle(button.dataset.aitFollowSymbol, button.dataset.aitFollowName);
  });

  window.AITWatchlist = {
    limit: FREE_LIMIT,
    getItems: read,
    getSymbols,
    isFollowed,
    toggle,
    refresh: refreshButtons
  };

  refreshButtons();
})();
