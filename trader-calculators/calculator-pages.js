(function(){
  const rupee = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });
  const pct = (n) => Number.isFinite(n) ? n.toFixed(2) + '%' : '-';
  const money = (n) => Number.isFinite(n) ? '₹' + rupee.format(n) : '-';
  const val = (card, name) => parseFloat(card.querySelector('[data-field="' + name + '"]')?.value || '0');
  const row = (label, value) => '<div><span>' + label + '</span><strong>' + value + '</strong></div>';
  const note = (text, tone='neutral') => '<p class="calc-note calc-note-' + tone + '">' + text + '</p>';
  function render(card, html){ const el=card.querySelector('.calc-result'); if(el) el.innerHTML = html; }
  function qualityLabel(score){
    if(score >= 72) return ['Strong result quality', 'positive'];
    if(score >= 52) return ['Mixed but acceptable', 'neutral'];
    return ['Weak / high reaction risk', 'warning'];
  }

  const sliderConfig = {
    averaging: {
      currentAvg:{min:1,max:5000,step:0.5}, currentQty:{min:1,max:10000,step:1},
      newPrice:{min:1,max:5000,step:0.5}, newQty:{min:1,max:10000,step:1}
    },
    stopLoss: {
      entry:{min:1,max:5000,step:0.5}, qty:{min:1,max:10000,step:1},
      sl:{min:1,max:5000,step:0.5}, target:{min:1,max:5000,step:0.5}
    },
    positionSize: {
      capital:{min:10000,max:5000000,step:1000}, riskPct:{min:0.1,max:10,step:0.1},
      entry:{min:1,max:5000,step:0.5}, sl:{min:1,max:5000,step:0.5}
    },
    resultReaction: {
      revenue:{min:-50,max:100,step:0.5}, profit:{min:-50,max:150,step:0.5},
      margin:{min:-10,max:10,step:0.1}, preMove:{min:-20,max:30,step:0.5}, pe:{min:0,max:150,step:0.5}
    },
    correctionRecovery: {
      high:{min:1,max:10000,step:1}, current:{min:1,max:10000,step:1}, avg:{min:1,max:10000,step:1}
    },
    targetRisk: {
      entry:{min:1,max:5000,step:0.5}, target:{min:1,max:5000,step:0.5},
      sl:{min:1,max:5000,step:0.5}, qty:{min:1,max:10000,step:1}
    },
    capitalAllocation: {
      capital:{min:10000,max:10000000,step:1000}, stocks:{min:1,max:30,step:1},
      cashPct:{min:0,max:80,step:1}, exposurePct:{min:1,max:100,step:1}
    }
  };

  function enhanceSliderFields(card){
    const type = card.dataset.calculator;
    const config = sliderConfig[type] || {};

    card.querySelectorAll('.calc-form-grid label').forEach(label => {
      const input = label.querySelector('input[data-field]');
      if(!input || label.classList.contains('calc-slider-field')) return;
      const field = input.dataset.field;
      const cfg = config[field] || {};
      const labelText = Array.from(label.childNodes).filter(n => n.nodeType === Node.TEXT_NODE).map(n => n.textContent).join(' ').trim();
      const min = cfg.min ?? parseFloat(input.getAttribute('min') || '0');
      const max = cfg.max ?? parseFloat(input.getAttribute('max') || '100');
      const step = cfg.step ?? parseFloat(input.getAttribute('step') || '1');
      const value = parseFloat(input.value || min);

      input.classList.add('calc-value-input');
      input.setAttribute('min', min);
      input.setAttribute('max', max);
      input.setAttribute('step', step);
      input.setAttribute('inputmode', 'decimal');

      const top = document.createElement('div');
      top.className = 'calc-slider-top';
      const name = document.createElement('span');
      name.className = 'calc-slider-label';
      name.textContent = labelText;

      const range = document.createElement('input');
      range.type = 'range';
      range.className = 'calc-range';
      range.min = min;
      range.max = max;
      range.step = step;
      range.value = Math.max(min, Math.min(max, Number.isFinite(value) ? value : min));
      range.setAttribute('aria-label', labelText);

      Array.from(label.childNodes).forEach(n => n.remove());
      top.appendChild(name);
      top.appendChild(input);
      label.appendChild(top);
      label.appendChild(range);
      label.className = 'calc-slider-field';

      const syncFromRange = () => {
        input.value = range.value;
        input.dispatchEvent(new Event('input', { bubbles: true }));
      };
      const syncFromInput = () => {
        let v = parseFloat(input.value || min);
        if(Number.isFinite(v)) range.value = Math.max(min, Math.min(max, v));
      };
      range.addEventListener('input', syncFromRange);
      input.addEventListener('input', syncFromInput);
    });
  }

  const calculators = {
    averaging(card){
      const ca=val(card,'currentAvg'), cq=val(card,'currentQty'), np=val(card,'newPrice'), nq=val(card,'newQty');
      const totalQty=cq+nq, totalInvest=(ca*cq)+(np*nq), newAvg=totalQty ? totalInvest/totalQty : 0;
      const bounceToAvg=np ? ((newAvg-np)/np)*100 : 0;
      const addedRisk=nq>0 ? (np*nq) : 0;
      const msg = nq > cq ? 'New buying is larger than existing quantity. Averaging is increasing exposure quickly.' : 'Averaging reduced the average price, but total capital at risk also increased.';
      render(card, row('New average price', money(newAvg)) + row('Total quantity', rupee.format(totalQty)) + row('Total investment', money(totalInvest)) + row('Bounce needed from new buy price', pct(bounceToAvg)) + row('Fresh capital added', money(addedRisk)) + note(msg, nq > cq ? 'warning':'neutral'));
    },
    stopLoss(card){
      const e=val(card,'entry'), q=val(card,'qty'), sl=val(card,'sl'), t=val(card,'target');
      const loss=(e-sl)*q, profit=(t-e)*q, rr=loss>0 ? profit/loss : 0;
      const msg = rr >= 2 ? 'Risk-reward looks healthy if the setup is valid.' : 'Risk-reward is weak. Consider avoiding or improving entry/stop placement.';
      render(card, row('Trade value', money(e*q)) + row('Maximum loss', money(loss)) + row('Potential profit', money(profit)) + row('Risk-reward ratio', Number.isFinite(rr) ? '1 : ' + rr.toFixed(2) : '-') + note(msg, rr >= 2 ? 'positive':'warning'));
    },
    positionSize(card){
      const c=val(card,'capital'), r=val(card,'riskPct'), e=val(card,'entry'), sl=val(card,'sl');
      const riskAmt=c*r/100, perShare=Math.abs(e-sl), qty=perShare ? Math.floor(riskAmt/perShare) : 0;
      const value=qty*e;
      render(card, row('Allowed risk amount', money(riskAmt)) + row('Risk per share', money(perShare)) + row('Suggested quantity', rupee.format(qty)) + row('Approx position value', money(value)) + note(qty <= 0 ? 'Stop loss distance is too large for the selected risk.' : 'Quantity is based only on risk limit, not conviction.', qty<=0?'warning':'neutral'));
    },
    resultReaction(card){
      const rev=val(card,'revenue'), prof=val(card,'profit'), margin=val(card,'margin'), pre=val(card,'preMove'), pe=val(card,'pe');
      let score=50 + Math.max(Math.min(rev,40),-40)*0.35 + Math.max(Math.min(prof,60),-60)*0.4 + Math.max(Math.min(margin*8,24),-24) - Math.max(pre,0)*1.1 - Math.max(pe-35,0)*0.35;
      score=Math.max(0,Math.min(100,score));
      const [label,tone]=qualityLabel(score);
      render(card, row('Result reaction score', score.toFixed(1) + ' / 100') + row('Interpretation', label) + row('Pre-result move impact', pre > 5 ? 'Already moved up' : 'Not heavily priced in') + row('Valuation risk', pe > 50 ? 'High' : pe > 30 ? 'Moderate' : 'Lower') + note('A good result can still fall if price already moved up or valuation is stretched.', tone));
    },
    correctionRecovery(card){
      const h=val(card,'high'), c=val(card,'current'), a=val(card,'avg');
      const fall=h ? ((h-c)/h)*100 : 0;
      const recover=c ? ((h-c)/c)*100 : 0;
      const avgBounce=c ? ((a-c)/c)*100 : 0;
      render(card, row('Fall from 52W high', pct(fall)) + row('Rise needed to revisit high', pct(recover)) + row('Bounce needed to reach your average', pct(avgBounce)) + note(fall > 30 ? 'Deep corrections need much bigger recovery than the fall percentage suggests.' : 'Correction is manageable, but trend confirmation is still important.', fall>30?'warning':'neutral'));
    },
    targetRisk(card){
      const e=val(card,'entry'), t=val(card,'target'), sl=val(card,'sl'), q=val(card,'qty');
      const upside=e ? ((t-e)/e)*100 : 0, downside=e ? ((e-sl)/e)*100 : 0;
      const profit=(t-e)*q, loss=(e-sl)*q, rr=loss>0 ? profit/loss : 0;
      render(card, row('Upside potential', pct(upside)) + row('Downside risk', pct(downside)) + row('Potential profit', money(profit)) + row('Potential loss', money(loss)) + row('Risk-reward ratio', Number.isFinite(rr) ? '1 : ' + rr.toFixed(2) : '-') + note(rr >= 2 ? 'Setup has reasonable reward compared with risk.' : 'Reward is not strong enough compared with risk.', rr>=2?'positive':'warning'));
    },
    capitalAllocation(card){
      const c=val(card,'capital'), s=Math.max(1, val(card,'stocks')), cash=val(card,'cashPct'), exp=val(card,'exposurePct');
      const cashAmt=c*cash/100, deploy=c-cashAmt, equal=deploy/s, maxPer=c*exp/100;
      const suggested=Math.min(equal,maxPer);
      render(card, row('Cash reserve', money(cashAmt)) + row('Deployable capital', money(deploy)) + row('Equal allocation per stock', money(equal)) + row('Max position cap', money(maxPer)) + row('Suggested per stock allocation', money(suggested)) + note(suggested < equal ? 'Exposure cap is limiting each position. This keeps concentration risk lower.' : 'Allocation is balanced across selected stocks.', suggested<equal?'positive':'neutral'));
    }
  };

  function runCard(card){
    const type = card.dataset.calculator;
    if(!type || !calculators[type]) return;
    enhanceSliderFields(card);
    const run = () => calculators[type](card);
    card.querySelector('.calc-button')?.addEventListener('click', run);
    card.querySelectorAll('input[data-field], .calc-range').forEach(input => input.addEventListener('input', run));
    run();
  }

  document.addEventListener('DOMContentLoaded', function(){
    document.querySelectorAll('[data-calculator]').forEach(runCard);
  });
})();
