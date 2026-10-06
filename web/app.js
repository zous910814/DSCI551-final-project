// PTCG Market frontend: a small hash-routed app that renders data from the REST API.
const main = document.getElementById('main');

const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
const money = (value, symbol = '$') => (value == null ? 'No price' : `${symbol}${Number(value).toFixed(2)}`);
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

async function api(path, options = {}) {
  const res = await fetch(`/api${path}`, {
    method: options.method || 'GET',
    headers: options.body ? { 'Content-Type': 'application/json' } : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.error || `Request failed (${res.status})`);
  return data;
}

function cardImage(url, size) {
  if (!url) return '<div class="card-image">No image</div>';
  return `<div class="card-image"><img src="${esc(url)}/${size}.webp" alt="" loading="lazy"
    onerror="this.parentNode.textContent='No image'"></div>`;
}

let metaCache = null;
async function meta() {
  if (!metaCache) metaCache = await api('/meta');
  return metaCache;
}

// ---------- Card Search ----------

const filters = { name: '', category: '', type: '', set: '', format: '', maxPrice: '', sort: 'price_desc', page: 1 };

async function renderSearch() {
  const m = await meta();
  const option = (value, label, current) =>
    `<option value="${esc(value)}"${value === current ? ' selected' : ''}>${esc(label)}</option>`;
  main.innerHTML = `
    <div class="heading">
      <h1>Card Search</h1>
      <p class="muted">${m.counts.cards.toLocaleString()} cards across ${m.counts.sets} sets.
        Prices as of ${esc(m.latestDate)}.</p>
    </div>
    <form class="panel filters" id="filters">
      <label class="field grow">Name<input id="f-name" placeholder="Search by name" value="${esc(filters.name)}"></label>
      <label class="field">Category<select id="f-category">
        ${option('', 'Any', filters.category)}${option('Pokemon', 'Pokémon', filters.category)}
        ${option('Trainer', 'Trainer', filters.category)}${option('Energy', 'Energy', filters.category)}</select></label>
      <label class="field">Type<select id="f-type">${option('', 'Any', filters.type)}
        ${m.types.map((t) => option(t, t, filters.type)).join('')}</select></label>
      <label class="field">Set<select id="f-set" style="max-width:190px">${option('', 'All sets', filters.set)}
        ${m.sets.map((s) => option(s.set_id, s.name, filters.set)).join('')}</select></label>
      <label class="field">Format<select id="f-format">${option('', 'Any', filters.format)}
        ${option('standard', 'Standard', filters.format)}${option('expanded', 'Expanded', filters.format)}</select></label>
      <label class="field">Max price (USD)<input id="f-maxPrice" type="number" min="0" step="0.01"
        style="width:130px" value="${esc(filters.maxPrice)}"></label>
      <button class="primary" type="submit">Search</button>
    </form>
    <div class="row between">
      <strong id="count"></strong>
      <label class="row muted">Sort
        <select id="f-sort" style="width:auto">
          ${option('price_desc', 'Price, high to low', filters.sort)}
          ${option('price_asc', 'Price, low to high', filters.sort)}
          ${option('name', 'Name', filters.sort)}</select></label>
    </div>
    <div class="grid" id="results"></div>
    <div class="pager" id="pager"></div>`;

  const read = () => {
    for (const key of ['name', 'category', 'type', 'set', 'format', 'maxPrice', 'sort']) {
      filters[key] = document.getElementById(`f-${key}`).value.trim();
    }
  };
  document.getElementById('filters').addEventListener('submit', (event) => {
    event.preventDefault();
    read();
    filters.page = 1;
    loadResults();
  });
  document.getElementById('f-sort').addEventListener('change', () => {
    read();
    filters.page = 1;
    loadResults();
  });
  await loadResults();
}

async function loadResults() {
  const results = document.getElementById('results');
  const params = new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== ''));
  const data = await api(`/cards?${params}`);
  document.getElementById('count').textContent = `${data.total.toLocaleString()} result${data.total === 1 ? '' : 's'}`;
  results.innerHTML = data.rows.map((row) => `
    <a class="tile" href="#/card/${encodeURIComponent(row.card_id)}">
      ${cardImage(row.image_url, 'low')}
      <div><div class="name">${esc(row.name)}</div><div class="set">${esc(row.set_name)}</div></div>
      <div class="row between"><span class="chip cap">${esc(row.variant_type)}</span>
        <span class="price${row.market_price == null ? ' muted small' : ''}">${money(row.market_price)}</span></div>
    </a>`).join('') || '<p class="notice">No cards match these filters.</p>';
  document.getElementById('pager').innerHTML = `
    <button id="prev"${data.page <= 1 ? ' disabled' : ''}>Previous</button>
    <span class="muted">Page ${data.page} of ${data.pages}</span>
    <button id="next"${data.page >= data.pages ? ' disabled' : ''}>Next</button>`;
  const go = (step) => () => { filters.page = data.page + step; loadResults(); window.scrollTo(0, 0); };
  document.getElementById('prev').addEventListener('click', go(-1));
  document.getElementById('next').addEventListener('click', go(1));
}

// ---------- Card Detail ----------

function priceChart(points) {
  if (points.length < 2) {
    return `<p class="notice small">${points.length ? `One snapshot so far (${esc(points[0].recorded_at)}).` : 'No price recorded.'}
      The trend appears once more daily snapshots are loaded.</p>`;
  }
  const values = points.map((p) => p.market_price);
  const min = Math.min(...values);
  const span = Math.max(...values) - min || 1;
  const xy = points.map((p, i) => [4 + (i / (points.length - 1)) * 292, 110 - ((p.market_price - min) / span) * 96]);
  const last = xy[xy.length - 1];
  return `<svg class="chart" viewBox="0 0 300 120" role="img"
      aria-label="Price from ${money(values[0])} to ${money(values[values.length - 1])}">
      <path d="M0 119.5H300" stroke="var(--line)"/>
      <polyline points="${xy.map((p) => p.join(',')).join(' ')}" fill="none" stroke="var(--blue)"
        stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
      <circle cx="${last[0]}" cy="${last[1]}" r="4" fill="var(--blue)"/></svg>
    <div class="row between small muted"><span>${esc(points[0].recorded_at)}</span>
      <span>${esc(points[points.length - 1].recorded_at)}</span></div>`;
}

const variantLabel = (v) => [v.variant_type, v.subtype, v.size !== 'standard' ? v.size : null, v.stamp]
  .filter(Boolean).join(', ');

async function renderCard(id) {
  const [{ card, types, attacks, variants, history }, decks] = await Promise.all([
    api(`/cards/${encodeURIComponent(id)}`), api('/decks')]);
  const priced = variants.find((v) => v.tcgplayer != null) || variants[0];
  const points = priced ? history.filter((h) => h.variant_id === priced.variant_id) : [];
  const stage = card.stage ? card.stage.replace(/^Stage(\d)$/, 'Stage $1') : card.stage;
  const pairs = [
    ['Set', card.set_name], ['Number', `${card.local_id}${card.card_count_official ? ` of ${card.card_count_official}` : ''}`],
    ['Category', card.category === 'Pokemon' ? 'Pokémon' : card.category], ['Type', types.join(', ')],
    ['HP', card.hp], ['Stage', stage && card.evolve_from ? `${stage}, from ${card.evolve_from}` : stage],
    ['Retreat cost', card.retreat_cost], ['Trainer type', card.trainer_type], ['Energy type', card.energy_type],
    ['Rarity', card.rarity], ['Illustrator', card.illustrator], ['Series', card.series_name],
  ].filter(([, value]) => value != null && value !== '');

  main.innerHTML = `
    <p class="muted"><a href="#/search">Card Search</a> &nbsp;/&nbsp; ${esc(card.set_name)} &nbsp;/&nbsp; ${esc(card.name)}</p>
    <div class="detail">
      <div class="detail-side">
        ${cardImage(card.image_url, 'high')}
        <section class="panel">
          <h2>Price history</h2>
          <p class="small muted">TCGplayer market price${priced ? `, ${esc(variantLabel(priced))}` : ''}</p>
          ${priceChart(points)}
        </section>
      </div>
      <div class="detail-main">
        <div class="row between" style="flex-wrap:wrap">
          <div>
            <h1>${esc(card.name)}</h1>
            <div class="row" style="gap:6px;margin-top:10px;flex-wrap:wrap">
              <span class="chip${card.is_standard ? ' good' : ''}">${card.is_standard ? 'Standard legal' : 'Not Standard legal'}</span>
              <span class="chip${card.is_expanded ? ' good' : ''}">${card.is_expanded ? 'Expanded legal' : 'Not Expanded legal'}</span>
              ${card.regulation_mark ? `<span class="chip">Regulation ${esc(card.regulation_mark)}</span>` : ''}
            </div>
          </div>
          <div class="row">
            <select id="deck-pick" style="width:auto" aria-label="Deck"${decks.length ? '' : ' disabled'}>
              ${decks.map((d) => `<option value="${d.deck_id}">${esc(d.deck_name)}</option>`).join('') || '<option>No decks yet</option>'}
            </select>
            <button class="primary" id="add-deck"${decks.length ? '' : ' disabled'}>Add to deck</button>
          </div>
        </div>
        <p class="notice" id="message" hidden></p>
        <section class="panel"><h2>Card details</h2>
          <dl class="pairs">${pairs.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>
        </section>
        ${attacks.length ? `<section class="panel"><h2>Attacks</h2>${attacks.map((a) => `
          <div class="attack">
            <div class="row between"><div class="row"><strong>${esc(a.name)}</strong>
              ${a.cost ? `<span class="chip">${esc(a.cost.replaceAll(',', ', '))}</span>` : ''}</div>
              <span class="damage">${esc(a.damage)}</span></div>
            ${a.effect ? `<p class="muted">${esc(a.effect)}</p>` : ''}
          </div>`).join('')}</section>` : ''}
        <h2>Latest prices by variant</h2>
        <div class="table-wrap"><table>
          <thead><tr><th>Variant</th><th class="right">TCGplayer (USD)</th><th class="right">Cardmarket (EUR)</th>
            <th class="right">7-day avg (EUR)</th><th></th></tr></thead>
          <tbody>${variants.map((v) => `<tr>
            <td class="strong" style="text-transform:capitalize">${esc(variantLabel(v))}</td>
            <td class="right${v.tcgplayer == null ? ' muted' : ' strong'}">${money(v.tcgplayer)}</td>
            <td class="right${v.cardmarket == null ? ' muted' : ''}">${money(v.cardmarket, '€')}</td>
            <td class="right${v.avg_7d == null ? ' muted' : ''}">${money(v.avg_7d, '€')}</td>
            <td class="right"><button data-variant="${v.variant_id}">Add to collection</button></td>
          </tr>`).join('') || '<tr><td colspan="5" class="muted">No variants recorded for this card.</td></tr>'}</tbody>
        </table></div>
      </div>
    </div>`;

  const say = (text) => {
    const box = document.getElementById('message');
    box.textContent = text;
    box.hidden = false;
  };
  document.getElementById('add-deck').addEventListener('click', async () => {
    const pick = document.getElementById('deck-pick');
    await api(`/decks/${pick.value}/cards`, { method: 'POST', body: { card_id: card.card_id, quantity: 1 } });
    say(`Added 1 × ${card.name} to ${pick.selectedOptions[0].textContent}.`);
  });
  main.querySelectorAll('[data-variant]').forEach((button) => button.addEventListener('click', async () => {
    await api('/collection', { method: 'POST', body: { variant_id: Number(button.dataset.variant) } });
    say(`Added 1 × ${card.name} to your collection.`);
  }));
}

// ---------- Decks ----------

async function renderDecks() {
  const decks = await api('/decks');
  main.innerHTML = `
    <div class="heading"><h1>Decks</h1>
      <p class="muted">Deck cost uses the cheapest variant of each card at the latest TCGplayer price.</p></div>
    <form class="panel filters" id="new-deck">
      <label class="field grow">New deck name<input id="deck-name" required placeholder="e.g. Dragapult ex"></label>
      <label class="field">Format<select id="deck-format"><option value="standard">Standard</option>
        <option value="expanded">Expanded</option><option value="unlimited">Unlimited</option></select></label>
      <button class="primary" type="submit">Create deck</button>
    </form>
    ${decks.length ? `<div class="table-wrap"><table>
      <thead><tr><th>Deck</th><th>Format</th><th class="right">Cards</th><th class="right">Cost</th><th></th></tr></thead>
      <tbody>${decks.map((d) => `<tr>
        <td class="strong"><a href="#/decks/${d.deck_id}">${esc(d.deck_name)}</a></td>
        <td style="text-transform:capitalize">${esc(d.format)}</td>
        <td class="right">${d.cards}</td><td class="right">${money(d.cost)}</td>
        <td class="right"><button class="link" data-delete="${d.deck_id}" data-name="${esc(d.deck_name)}">Delete</button></td>
      </tr>`).join('')}</tbody></table></div>` : '<p class="notice">No decks yet. Create one above, then add cards to it.</p>'}`;

  document.getElementById('new-deck').addEventListener('submit', async (event) => {
    event.preventDefault();
    const created = await api('/decks', { method: 'POST', body: {
      name: document.getElementById('deck-name').value, format: document.getElementById('deck-format').value } });
    location.hash = `#/decks/${created.deck_id}`;
  });
  main.querySelectorAll('[data-delete]').forEach((button) => button.addEventListener('click', async () => {
    if (button.dataset.armed !== 'yes') {
      button.dataset.armed = 'yes';
      button.textContent = `Delete ${button.dataset.name}?`;
      return;
    }
    await api(`/decks/${button.dataset.delete}`, { method: 'DELETE' });
    renderDecks();
  }));
}

async function renderDeck(id) {
  const { deck, cards } = await api(`/decks/${id}`);
  const legal = (c) => deck.format === 'unlimited' || (deck.format === 'standard' ? c.is_standard : c.is_expanded);
  const count = cards.reduce((sum, c) => sum + c.quantity, 0);
  const cost = cards.reduce((sum, c) => sum + c.quantity * (c.unit_price || 0), 0);
  const unpriced = cards.filter((c) => c.unit_price == null).length;
  const illegal = cards.filter((c) => !legal(c));
  const toBuy = cards.map((c) => ({ ...c, need: Math.max(0, c.quantity - c.owned) })).filter((c) => c.need > 0);
  const buyCost = toBuy.reduce((sum, c) => sum + c.need * (c.unit_price || 0), 0);
  const byCategory = (name) => cards.filter((c) => c.category === name).reduce((sum, c) => sum + c.quantity, 0);

  main.innerHTML = `
    <div class="row between" style="align-items:flex-end;flex-wrap:wrap">
      <div class="heading"><h1>${esc(deck.deck_name)}</h1>
        <p class="muted"><a href="#/decks">Decks</a> &nbsp;/&nbsp; <span style="text-transform:capitalize">${esc(deck.format)}</span> format</p></div>
      <div class="suggest" style="width:320px">
        <input id="add-card" placeholder="Add a card by name" autocomplete="off" aria-label="Add a card by name">
        <ul id="suggestions" hidden></ul>
      </div>
    </div>
    <div class="stats">
      <div class="panel stat"><span class="label">Deck cost (TCGplayer)</span><span class="value">${money(cost)}</span>
        <span class="small muted">${unpriced ? `${plural(unpriced, 'card')} without a price not counted` : 'Cheapest variant of each card'}</span></div>
      <div class="panel stat"><span class="label">Cards</span><span class="value">${count} / 60</span>
        <span class="small muted">${byCategory('Pokemon')} Pokémon, ${byCategory('Trainer')} Trainer, ${byCategory('Energy')} Energy</span></div>
      <div class="panel stat"><span class="label">Not ${esc(deck.format)} legal</span>
        <span class="value${illegal.length ? ' bad' : ''}">${plural(illegal.length, 'card')}</span>
        <span class="small muted">${illegal.length ? esc(illegal.map((c) => c.name).slice(0, 3).join(', ')) : 'Every card is legal'}</span></div>
      <div class="panel stat"><span class="label">Missing from collection</span>
        <span class="value">${plural(toBuy.reduce((sum, c) => sum + c.need, 0), 'card')}</span>
        <span class="small muted">${money(buyCost)} to complete</span></div>
    </div>
    <div class="deck-body">
      <div class="table-wrap grow">${cards.length ? `<table>
        <thead><tr><th>Qty</th><th>Card</th><th>Set</th><th>Category</th><th style="text-transform:capitalize">${esc(deck.format)}</th>
          <th class="right">Unit</th><th class="right">Subtotal</th><th></th></tr></thead>
        <tbody>${cards.map((c) => `<tr>
          <td><input class="qty" type="number" min="0" max="60" value="${c.quantity}" data-card="${esc(c.card_id)}"
            aria-label="Quantity of ${esc(c.name)}"></td>
          <td class="strong"><a href="#/card/${encodeURIComponent(c.card_id)}">${esc(c.name)}</a></td>
          <td>${esc(c.set_name)}</td><td>${c.category === 'Pokemon' ? 'Pokémon' : esc(c.category)}</td>
          <td class="${legal(c) ? 'good' : 'bad'}">${legal(c) ? 'Legal' : 'Not legal'}</td>
          <td class="right${c.unit_price == null ? ' muted' : ''}">${money(c.unit_price)}</td>
          <td class="right">${c.unit_price == null ? '' : money(c.quantity * c.unit_price)}</td>
          <td class="right"><button class="link" data-remove="${esc(c.card_id)}">Remove</button></td>
        </tr>`).join('')}</tbody></table>` : '<p class="notice" style="margin:16px">This deck is empty. Add a card by name above.</p>'}</div>
      <section class="panel side"><h2>Cards to buy</h2>
        <p class="small muted">Needed for this deck but not in your collection.</p>
        <div class="list">${toBuy.map((c) => `<div class="row between"><span>${esc(c.name)} × ${c.need}</span>
          <span>${c.unit_price == null ? '<span class="muted">No price</span>' : money(c.need * c.unit_price)}</span></div>`).join('')
          || '<span class="muted">You own every card in this deck.</span>'}
          ${toBuy.length ? `<div class="row between total"><span>Total</span><span>${money(buyCost)}</span></div>` : ''}</div>
      </section>
    </div>`;

  const setQuantity = async (cardId, quantity) => {
    await api(`/decks/${id}/cards/${encodeURIComponent(cardId)}`, { method: 'PUT', body: { quantity } });
    renderDeck(id);
  };
  main.querySelectorAll('input.qty').forEach((input) => input.addEventListener('change', () =>
    setQuantity(input.dataset.card, Number(input.value) || 0)));
  main.querySelectorAll('[data-remove]').forEach((button) => button.addEventListener('click', () =>
    setQuantity(button.dataset.remove, 0)));

  const box = document.getElementById('add-card');
  const list = document.getElementById('suggestions');
  let timer = null;
  box.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const found = box.value.trim() ? await api(`/cards/suggest?name=${encodeURIComponent(box.value.trim())}`) : [];
      list.innerHTML = found.map((c) => `<li><button data-add="${esc(c.card_id)}">${esc(c.name)}
        <span class="muted small">${esc(c.set_name)} #${esc(c.local_id)}</span></button></li>`).join('');
      list.hidden = !found.length;
      list.querySelectorAll('[data-add]').forEach((button) => button.addEventListener('click', async () => {
        await api(`/decks/${id}/cards`, { method: 'POST', body: { card_id: button.dataset.add, quantity: 1 } });
        renderDeck(id);
      }));
    }, 200);
  });
}

// ---------- Query Lab ----------

const DESIGNS = [
  ['none', 'No index'],
  ['price', '(market_price)'],
  ['eq_first', '(marketplace_id, recorded_at, market_price)'],
  ['range_first', '(market_price, marketplace_id, recorded_at)'],
];
const lab = { selected: 'eq_first', cap: '5.00', marketplace: '1', data: null };

function planSummary(plan, result) {
  const access = plan.match(/(Table scan|Index range scan|Index lookup|Covering index \w+|Index scan) on p\b[^\n(]*/i);
  const joins = [/nested loop/i.test(plan) && 'Nested loop', /hash join/i.test(plan) && 'Hash join'].filter(Boolean);
  return [
    ['Access to price table', access ? access[0].trim() : 'See plan'],
    ['Sort', /Sort:/.test(plan) ? 'Explicit sort' : 'None, index order'],
    ['Join', joins.join(' + ') || 'See plan'],
    ['Rows returned', result.rows.toLocaleString()],
    ['Median time (5 runs)', `${result.ms} ms`],
  ];
}

function renderLabResults() {
  const out = document.getElementById('lab-out');
  if (!lab.data) {
    out.innerHTML = '<p class="notice">Run the query to see its execution plan. “Compare all” measures every index design.</p>';
    return;
  }
  const { sql, tableRows, results } = lab.data;
  const shown = results.find((r) => r.design === lab.selected) || results[0];
  const slowest = Math.max(...results.map((r) => r.ms));
  out.innerHTML = `
    <div class="lab-body">
      <div class="stack grow" style="gap:16px">
        <section class="code"><h2>SQL</h2><pre>${esc(sql)}</pre></section>
        <section class="code"><h2>EXPLAIN ANALYZE, index ${esc(shown.index || 'none')}</h2><pre>${esc(shown.plan)}</pre></section>
      </div>
      <div class="side">
        <section class="panel"><h2>Execution time</h2>
          <p class="small muted">Measured on price_exp (${tableRows.toLocaleString()} rows), median of 5 runs.</p>
          ${results.map((r) => `<div class="bar${r.design === shown.design ? ' active' : ''}">
            <span class="label">${esc(r.index || 'No index')}</span>
            <div class="track"><span class="fill" style="width:${Math.round((r.ms / slowest) * 240)}px"></span>${r.ms} ms</div>
          </div>`).join('')}
        </section>
        <section class="panel"><h2>Plan summary</h2>
          <dl class="pairs" style="grid-template-columns:1fr">${planSummary(shown.plan, shown)
            .map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>
        </section>
      </div>
    </div>`;
}

async function renderLab() {
  main.innerHTML = `
    <div class="heading"><h1>Query Lab</h1>
      <p class="muted">Run a workload query under different index designs and compare the execution plans.</p></div>
    <form class="panel filters" id="lab-form">
      <label class="field grow">Query<select disabled>
        <option>Q2 &nbsp; Standard-legal Pokémon under a price cap, sorted by price</option></select></label>
      <label class="field">Marketplace<select id="lab-market"><option value="1">TCGplayer</option>
        <option value="2">Cardmarket</option></select></label>
      <label class="field">Price cap<input id="lab-cap" type="number" min="0" step="0.01" style="width:130px" required></label>
      <button type="submit" class="primary">Run query</button>
      <button type="button" id="lab-all">Compare all</button>
    </form>
    <div class="stack" style="gap:8px">
      <span class="small muted">Index design on price_exp, an index-free copy of price_history</span>
      <div class="options">${DESIGNS.map(([key, label]) => `<button type="button" data-design="${key}">${esc(label)}</button>`).join('')}</div>
    </div>
    <div id="lab-out"></div>`;
  document.getElementById('lab-cap').value = lab.cap;
  document.getElementById('lab-market').value = lab.marketplace;

  const mark = () => main.querySelectorAll('[data-design]').forEach((button) =>
    button.classList.toggle('active', button.dataset.design === lab.selected));
  const run = async (designs) => {
    lab.cap = document.getElementById('lab-cap').value;
    lab.marketplace = document.getElementById('lab-market').value;
    const out = document.getElementById('lab-out');
    out.innerHTML = '<p class="notice">Building the index and running the query…</p>';
    try {
      lab.data = await api('/lab/run', { method: 'POST', body: {
        designs, cap: Number(lab.cap), marketplace: Number(lab.marketplace) } });
      renderLabResults();
    } catch (err) {
      out.innerHTML = `<p class="notice error">${esc(err.message)}</p>`;
    }
  };
  main.querySelectorAll('[data-design]').forEach((button) => button.addEventListener('click', () => {
    lab.selected = button.dataset.design;
    mark();
    if (lab.data && lab.data.results.some((r) => r.design === lab.selected)) renderLabResults();
    else run([lab.selected]);
  }));
  document.getElementById('lab-form').addEventListener('submit', (event) => {
    event.preventDefault();
    run([lab.selected]);
  });
  document.getElementById('lab-all').addEventListener('click', () => run(DESIGNS.map(([key]) => key)));
  for (const field of ['lab-cap', 'lab-market']) {
    document.getElementById(field).addEventListener('change', () => { lab.data = null; });
  }
  mark();
  renderLabResults();
}

// ---------- Router ----------

async function router() {
  const [, page = 'search', arg] = location.hash.split('/');
  const nav = page === 'card' ? 'search' : page;
  document.querySelectorAll('[data-nav]').forEach((link) => link.classList.toggle('active', link.dataset.nav === nav));
  main.innerHTML = '<p class="muted">Loading…</p>';
  try {
    if (page === 'card' && arg) await renderCard(decodeURIComponent(arg));
    else if (page === 'decks' && arg) await renderDeck(arg);
    else if (page === 'decks') await renderDecks();
    else if (page === 'lab') await renderLab();
    else await renderSearch();
  } catch (err) {
    main.innerHTML = `<p class="notice error">${esc(err.message)}</p>`;
  }
}

window.addEventListener('hashchange', router);
router();
