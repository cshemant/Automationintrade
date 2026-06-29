(function(){
  const DATA_URL = '/market-data/sector-wise-stocks.json?ts=' + Date.now();
  const money = (v) => '₹' + Number(v || 0).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const pct = (v) => (Number(v || 0) > 0 ? '+' : '') + Number(v || 0).toFixed(2) + '%';
  const cls = (v) => Number(v || 0) >= 0 ? 'is-positive' : 'is-negative';
  const esc = (s) => String(s ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

  function bindIndexSearch(){
    const input = document.getElementById('sectorSearchInput');
    const rows = [...document.querySelectorAll('.sector-list-row')];
    if(input) input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
      rows.forEach(row => { row.style.display = !q || (row.dataset.sectorName || '').includes(q) ? 'grid' : 'none'; });
    });
  }

  function bindStockSearch(){
    const input = document.getElementById('stockSectorSearch');
    const rows = [...document.querySelectorAll('#sectorStockRows tr')];
    if(input) input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
      rows.forEach(row => { row.style.display = !q || row.textContent.toLowerCase().includes(q) ? '' : 'none'; });
    });
  }

  function renderIndex(data){
    const wrap = document.querySelector('[data-sector-index]');
    if(!wrap) return;
    const count = wrap.querySelector('.sector-count');
    if(count) count.textContent = `${data.sectorCount || 0} sectors · ${data.stockCount || 0} stocks`;
    const note = wrap.querySelector('.sector-data-note');
    if(note) note.innerHTML = `Updated: ${esc(data.updatedAt || '')}<br>Source: Latest AIT stock strength universe`;
    const rows = document.getElementById('sectorListRows');
    if(!rows) return;
    rows.innerHTML = (data.sectors || []).map(sector => {
      const top = (sector.stocks && sector.stocks[0]) ? sector.stocks[0].stockName : '-';
      return `<a class="sector-list-row" href="/markets/sector/${esc(sector.slug)}/" data-sector-name="${esc(String(sector.name || '').toLowerCase())}">
        <span class="sector-name">${esc(sector.name)}</span>
        <span>${sector.stockCount || 0} stocks</span>
        <span>${Number(sector.avgStrength || 0).toFixed(1)}</span>
        <span>${esc(top)}</span>
      </a>`;
    }).join('');
    bindIndexSearch();
  }

  function renderDetail(data){
    const wrap = document.querySelector('[data-sector-detail]');
    if(!wrap) return;
    const slug = wrap.dataset.sectorDetail;
    const sector = (data.sectors || []).find(s => s.slug === slug);
    if(!sector) return;
    const top = (sector.stocks && sector.stocks[0]) ? sector.stocks[0].stockName : '-';
    const count = wrap.querySelector('.sector-count');
    if(count) count.textContent = `${sector.stockCount || 0} companies · Average AIT score ${Number(sector.avgStrength || 0).toFixed(1)}`;
    const note = wrap.querySelector('.sector-data-note');
    if(note) note.innerHTML = `Strongest in this group:<br><strong>${esc(top)}</strong>`;
    const stats = wrap.querySelector('.sector-stats-grid');
    if(stats) stats.innerHTML = `
      <div><span>Stocks tracked</span><strong>${sector.stockCount || 0}</strong></div>
      <div><span>Avg AIT score</span><strong>${Number(sector.avgStrength || 0).toFixed(1)}</strong></div>
      <div><span>Strong stocks</span><strong>${sector.strongCount || 0}</strong></div>
      <div><span>Updated</span><strong>${esc(data.updatedAt || '')}</strong></div>`;
    const body = document.getElementById('sectorStockRows');
    if(body) body.innerHTML = (sector.stocks || []).map((stock, i) => {
      const change = Number(stock.changePct || 0);
      const down = Number(stock.downFromHighPct || 0);
      const symbol = stock.symbol || '';
      return `<tr>
        <td class="sector-rank">${i + 1}</td>
        <td><strong>${esc(stock.stockName)}</strong><small>${esc(symbol)}</small></td>
        <td>${money(stock.cmp)}</td>
        <td class="${cls(change)}">${pct(change)}</td>
        <td>${money(stock.high52)}</td>
        <td class="${cls(down)}">${pct(down)}</td>
        <td><span class="sector-score-pill">${Number(stock.strengthScore || 0).toFixed(1)}</span></td>
        <td>${esc(stock.signal)}</td>
        <td><a class="sector-table-link" href="/?stock=${encodeURIComponent(symbol)}&research=technical-analysis">Analyze</a></td>
      </tr>`;
    }).join('');
    bindStockSearch();
  }

  fetch(DATA_URL, {cache: 'no-store'})
    .then(r => r.ok ? r.json() : Promise.reject(r.status))
    .then(data => { renderIndex(data); renderDetail(data); })
    .catch(() => { bindIndexSearch(); bindStockSearch(); });
})();
