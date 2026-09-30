/* Система автоматического реферирования документов (sentence extraction + OSTIS).
   Клиентская часть: обращения к API, отрисовка вкладок, интерактивные элементы. */
'use strict';

const TABS = [
  { id: 'abstract', label: 'Реферат' },
  { id: 'heat', label: 'Карта текста' },
  { id: 'terms', label: 'Термины' },
  { id: 'graph', label: 'Сеть OSTIS' },
  { id: 'compare', label: 'Сравнение' },
  { id: 'batch', label: 'Коллекция' },
  { id: 'stats', label: 'Статистика' },
  { id: 'help', label: 'Справка' },
];

const DEFAULTS = {
  sentences: 10, keywords: 15, method: 'tfidf', alpha: 1, beta: 1,
  mmr_lambda: 1, length_norm: 'none', conflate_stems: true,
};

const state = {
  collection: null,      // ответ /api/collection
  docId: null,           // выбранный документ коллекции
  custom: null,          // {title, text, source} — документ вне коллекции
  data: null,            // ответ /api/analyze
  currentSentence: null, // разбираемое предложение на карте текста
  focusTerm: null,       // термин, подсвеченный в тексте
  termSort: { key: 'weight', dir: -1 },
  batchRows: null,
  batchSort: { key: 'title', dir: 1 },
  statsSort: { key: 'title', dir: 1 },
  stats: null,
  collectionGraph: null,
  graphScope: 'document',
  graphRotate: 0,
  helpLoaded: false,
  busy: 0,
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmt = (x, n = 2) => Number(x).toFixed(n);
const num = (x) => Number(x).toLocaleString('ru-RU');
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

function toast(message, ms = 2600) {
  const el = $('#toast');
  el.textContent = message;
  el.classList.add('show');
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove('show'), ms);
}

function busy(on) {
  state.busy = Math.max(0, state.busy + (on ? 1 : -1));
  $('#progress').hidden = state.busy === 0;
  document.body.classList.toggle('busy', state.busy > 0);
}

/* --------------------------- параметры расчёта --------------------------- */
function params() {
  return {
    sentences: +$('#p-sent').value,
    keywords: +$('#p-kw').value,
    method: $('#p-method').value,
    alpha: +$('#p-alpha').value,
    beta: +$('#p-beta').value,
    mmr_lambda: +$('#p-mmr').value,
    length_norm: $('#p-lennorm').value,
    conflate_stems: $('#p-conflate').checked,
  };
}

function markChangedParams() {
  const current = params();
  const changed = Object.keys(DEFAULTS).some((k) => current[k] !== DEFAULTS[k]);
  $('#params-changed').hidden = !changed;
  if (changed && !$('#adv-params').open
      && ['alpha', 'beta', 'mmr_lambda', 'length_norm', 'conflate_stems']
        .some((k) => current[k] !== DEFAULTS[k])) {
    $('#adv-params').open = true;
  }
}

function resetParams() {
  $('#p-sent').value = DEFAULTS.sentences;
  $('#p-kw').value = DEFAULTS.keywords;
  $('#p-method').value = DEFAULTS.method;
  $('#p-alpha').value = DEFAULTS.alpha;
  $('#p-beta').value = DEFAULTS.beta;
  $('#p-mmr').value = DEFAULTS.mmr_lambda;
  $('#p-lennorm').value = DEFAULTS.length_norm;
  $('#p-conflate').checked = DEFAULTS.conflate_stems;
  syncSliderLabels();
  markChangedParams();
  state.collectionGraph = null;
  analyze();
  toast('Параметры возвращены к формуле методических указаний');
}

function requestBody(extra = {}) {
  const body = { ...params(), ...extra };
  if (state.custom) {
    body.text = state.custom.text;
    body.title = state.custom.title;
    body.source = state.custom.source || '';
  } else {
    body.doc_id = state.docId;
  }
  return body;
}

async function api(path, body) {
  const options = body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok || data.error) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

/* ------------------------------- коллекция ------------------------------- */
async function loadCollection(selectId) {
  const info = await api('/api/collection');
  state.collection = info;
  $('#db-size').textContent = `|DB| = ${info.size}`;
  $('#coll-stats').innerHTML =
    `Индексация: ${fmt(info.index_time_ms, 0)} мс · склеено основ: ${info.stem_map_size}`;
  renderDocList();
  const ids = info.documents.map((d) => d.id);
  const target = selectId && ids.includes(selectId) ? selectId
    : (state.docId && ids.includes(state.docId) ? state.docId : ids[0]);
  if (target && !state.custom) selectDocument(target);
  else if (target && selectId) selectDocument(target);
}

function renderDocList() {
  const query = ($('#doc-search').value || '').toLowerCase().trim();
  const list = $('#doclist');
  list.innerHTML = '';
  let shown = 0;
  state.collection.documents.forEach((doc) => {
    const match = !query || doc.title.toLowerCase().includes(query)
      || (doc.domain || '').toLowerCase().includes(query) || doc.id.includes(query);
    if (!match) return;
    shown++;
    const button = document.createElement('button');
    button.className = 'doc' + (doc.id === state.docId && !state.custom ? ' active' : '');
    button.dataset.id = doc.id;
    button.innerHTML =
      `<div class="t">${esc(doc.title)}</div>
       <div class="m"><span class="badge ${doc.language}">${doc.language}</span>
         <span>${esc(doc.domain || '—')}</span><span>· ${num(doc.chars)} симв.</span>
         <span>· ${doc.sentences} предл.</span>
         ${doc.added_by_user ? '<span class="badge">свой</span>' : ''}</div>`;
    button.onclick = () => selectDocument(doc.id);
    if (doc.added_by_user) {
      const del = document.createElement('button');
      del.className = 'del';
      del.title = 'Удалить документ из коллекции';
      del.textContent = '×';
      del.onclick = (event) => { event.stopPropagation(); removeDocument(doc); };
      button.appendChild(del);
    }
    list.appendChild(button);
  });
  if (!shown) list.innerHTML = '<div class="empty">Ничего не найдено. Измените запрос.</div>';
  const active = list.querySelector('.doc.active');
  if (active) active.scrollIntoView({ block: 'nearest' });
}

function selectDocument(id) {
  state.docId = id;
  state.custom = null;
  state.currentSentence = null;
  state.focusTerm = null;
  $$('.doc').forEach((b) => b.classList.toggle('active', b.dataset.id === id));
  analyze();
}

function useCustomDocument(custom) {
  state.custom = custom;
  state.docId = null;
  state.currentSentence = null;
  state.focusTerm = null;
  $$('.doc').forEach((b) => b.classList.remove('active'));
  analyze();
}

/* Любой новый текст (вставленный, из файла или загруженный по ссылке)
   сразу становится полноценным документом коллекции: он сохраняется на диск,
   |DB| увеличивается, а df(t) и веса терминов пересчитываются для всех
   документов. Если сохранить не удалось, документ обрабатывается временно. */
async function addTextToCollection({ title, text, source = '', language = '' }) {
  busy(true);
  try {
    const result = await api('/api/collection/add', { text, title, source, language });
    state.custom = null;
    state.collectionGraph = null;
    state.batchRows = null;
    state.stats = null;
    await loadCollection(result.document.id);
    if (result.document.existing) {
      toast('Такой документ уже есть в коллекции — открыт существующий', 4000);
    } else {
      toast(`«${result.document.title}» добавлен в коллекцию: |DB| = ${result.collection.size}, ` +
            'документные частоты df(t) пересчитаны', 4600);
    }
    return true;
  } catch (error) {
    toast('Документ не сохранён в коллекцию (' + error.message +
          '), обрабатывается временно', 5200);
    useCustomDocument({ title, text, source });
    return false;
  } finally {
    busy(false);
  }
}

async function addCurrentToCollection() {
  if (!state.custom) return;
  busy(true);
  try {
    const result = await api('/api/collection/add', {
      text: state.custom.text, title: state.custom.title,
      source: state.custom.source || '', language: state.data?.document.language || '',
    });
    state.custom = null;
    state.collectionGraph = null;
    state.batchRows = null;
    state.stats = null;
    await loadCollection(result.document.id);
    toast(`Документ добавлен в коллекцию: |DB| = ${result.collection.size}, ` +
          'документные частоты df(t) пересчитаны', 4200);
  } catch (error) {
    toast('Не удалось добавить документ: ' + error.message, 5000);
  } finally {
    busy(false);
  }
}

function removeDocument(doc) {
  confirmDialog(`Удалить «${doc.title}» из коллекции?`,
    'Файл документа будет удалён с диска, |DB| уменьшится, ' +
    'документные частоты df(t) и веса терминов пересчитаются.', async () => {
      busy(true);
      try {
        const result = await api('/api/collection/remove', { id: doc.id });
        state.collectionGraph = null;
        state.batchRows = null;
        state.stats = null;
        if (state.docId === doc.id) state.docId = null;
        await loadCollection();
        toast(`Документ удалён: |DB| = ${result.collection.size}`);
      } catch (error) {
        toast('Не удалось удалить: ' + error.message, 5000);
      } finally {
        busy(false);
      }
    });
}

/* -------------------------------- анализ -------------------------------- */
let pending = null;

async function analyze() {
  const body = requestBody();
  if (!body.doc_id && !body.text) return;
  if (pending) pending.abort();
  pending = new AbortController();
  busy(true);
  const started = performance.now();
  try {
    const response = await fetch('/api/analyze', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body), signal: pending.signal,
    });
    const data = await response.json();
    if (data.error) { toast('Ошибка: ' + data.error, 6000); return; }
    data.client_ms = performance.now() - started;
    state.data = data;
    if (state.graphScope !== 'collection') state.collectionGraph = state.collectionGraph;
    renderAll();
  } catch (error) {
    if (error.name !== 'AbortError') toast('Сбой запроса: ' + error.message, 6000);
  } finally {
    busy(false);
  }
}

const analyzeSoon = debounce(analyze, 200);

function renderAll() {
  const collectionScope = state.graphScope === 'collection' && state.collectionGraph;
  renderDocBar();
  renderAbstract();
  renderHeat();
  renderTerms();
  renderGraph(collectionScope ? state.collectionGraph.graph : state.data.graph);
  renderScs(collectionScope ? state.collectionGraph.scs : state.data.scs);
  renderCompare();
}

/* ---------------------------- шапка документа ---------------------------- */
function renderDocBar() {
  const d = state.data, doc = d.document, q = d.quality;
  $('#d-title').textContent = doc.title;
  $('#d-lang').textContent = doc.language === 'ru' ? 'русский' : 'английский';
  $('#d-lang').className = 'badge ' + doc.language;
  $('#d-domain').textContent = doc.domain || 'без предметной области';

  const source = $('#d-source');
  if (doc.source) {
    source.href = doc.source;
    source.textContent = doc.source.length > 60 ? 'источник ↗' : doc.source;
    source.hidden = false;
  } else source.hidden = true;

  $('#d-temp').hidden = !state.custom;
  const addButton = $('#btn-add-collection');
  addButton.hidden = !state.custom;
  addButton.textContent = `＋ Добавить в коллекцию (|DB| станет ${d.params.db_size})`;

  const stats = [
    ['символов', num(doc.chars)], ['слов', num(doc.words)],
    ['значимых слов', num(doc.significant_words)], ['абзацев', doc.paragraphs],
    ['предложений', doc.sentences], ['терминов', num(doc.terms)],
    ['сжатие', (q.compression * 100).toFixed(1) + '%'],
    ['покрытие кл. слов', (q.keyword_coverage * 100).toFixed(0) + '%'],
    ['время, мс', fmt(d.timings.total_ms, 1)],
  ];
  $('#d-stats').innerHTML = stats.map(([k, v]) =>
    `<div class="stat"><div class="v">${v}</div><div class="k">${k}</div></div>`).join('');
}

/* --------------------------------- реферат -------------------------------- */
function renderAbstract() {
  const d = state.data;
  const alpha = d.params.alpha, beta = d.params.beta;
  const pdLabel = alpha === 1 ? 'Posd' : `Posd^${alpha}`;
  const ppLabel = beta === 1 ? 'Posp' : `Posp^${beta}`;
  const byIndex = Object.fromEntries(d.sentences.map((s) => [s.index, s]));
  const maxWeight = Math.max(...d.summary.indices.map((i) => byIndex[i].weight), 1e-9);

  $('#sum-note').textContent =
    `${d.summary.indices.length} предложений из ${d.document.sentences}; метод: ${d.params.method_title}`;

  $('#summary-list').innerHTML = d.summary.indices.map((i) => {
    const s = byIndex[i];
    return `<li data-i="${i}"><span>${esc(s.text)}</span>
      <div class="meta">предложение №${i + 1} · W = ${fmt(s.weight)} =
        ${pdLabel} ${fmt(Math.pow(s.posd, alpha), 3)} ×
        ${ppLabel} ${fmt(Math.pow(s.posp, beta), 3)} × Score ${fmt(s.score)}
        <span class="wbar" style="width:${(s.weight / maxWeight * 90).toFixed(1)}px"></span>
        <a href="#heat" class="showin" data-i="${i}">показать в тексте →</a></div></li>`;
  }).join('');
  $$('#summary-list .showin').forEach((link) => {
    link.onclick = (event) => {
      event.preventDefault();
      showTab('heat');
      showSentence(+link.dataset.i);
      const target = $(`#heattext .sent[data-i="${link.dataset.i}"]`);
      if (target) target.scrollIntoView({ block: 'center', behavior: 'smooth' });
    };
  });
  $('#summary-plain').textContent = d.summary.text;

  const maxKw = d.keywords.length ? d.keywords[0].weight : 1;
  $('#kw-chips').innerHTML = d.keywords.map((k, i) =>
    `<button class="chip" data-term="${esc(k.term)}"
       title="основа: ${esc(k.term)}; tf=${k.tf}; df=${k.df}; IDF=${fmt(k.idf, 3)} — щёлкните, чтобы найти в тексте"
       style="font-size:${(12 + 7 * k.weight / maxKw).toFixed(1)}px">
       ${i + 1}. ${esc(k.form)} <b>${fmt(k.weight, 2)}</b></button>`).join('');
  $$('#kw-chips .chip').forEach((chip) => {
    chip.onclick = () => focusTerm(chip.dataset.term);
  });
}

/* ------------------------------ карта текста ------------------------------ */
function renderHeat() {
  const d = state.data, text = d.text || '';
  const chosen = new Set(d.summary.indices);
  const maxWeight = Math.max(...d.sentences.map((s) => s.weight), 1e-9);

  let html = '', cursor = 0;
  const flush = (upTo) => {
    html += esc(text.slice(cursor, upTo)).replace(/\n{2,}/g, '</p><p>').replace(/\n/g, ' ');
    cursor = upTo;
  };
  d.sentences.forEach((s) => {
    flush(s.start);
    const alpha = Math.pow(s.weight / maxWeight, 0.75) * 0.5;
    const picked = chosen.has(s.index);
    const color = picked ? `rgba(184,86,47,${(0.18 + alpha).toFixed(3)})`
                         : `rgba(47,93,140,${alpha.toFixed(3)})`;
    html += `<span class="sent${picked ? ' picked' : ''}" data-i="${s.index}"
      style="background:${color}"
      title="W=${fmt(s.weight)} (Posd ${fmt(s.posd, 2)} × Posp ${fmt(s.posp, 2)} × Score ${fmt(s.score, 1)})"
      >${esc(text.slice(s.start, s.end))}</span>`;
    cursor = s.end;
  });
  flush(text.length);
  $('#heattext').innerHTML = '<p>' + html + '</p>';
  $$('#heattext .sent').forEach((el) => { el.onclick = () => showSentence(+el.dataset.i); });

  const minimap = $('#minimap');
  minimap.innerHTML = d.sentences.map((s) => {
    const top = (s.start / (d.document.chars || 1) * 100).toFixed(2);
    const height = Math.max(0.4, (s.end - s.start) / (d.document.chars || 1) * 100);
    const alpha = Math.pow(s.weight / maxWeight, 0.6);
    const color = chosen.has(s.index) ? '#b8562f' : '#2f5d8c';
    return `<div title="№${s.index + 1}: W=${fmt(s.weight)}" data-i="${s.index}"
      style="top:${top}%;height:${height.toFixed(2)}%;background:${color};opacity:${(0.15 + 0.85 * alpha).toFixed(2)}"></div>`;
  }).join('');
  $$('#minimap div').forEach((el) => {
    el.onclick = () => {
      const target = $(`#heattext .sent[data-i="${el.dataset.i}"]`);
      if (target) target.scrollIntoView({ block: 'center', behavior: 'smooth' });
      showSentence(+el.dataset.i);
    };
  });

  applyTermFocus();
  if (state.currentSentence !== null) showSentence(state.currentSentence);
  else $('#sent-detail').innerHTML =
    '<div class="hint">Предложение не выбрано. Щёлкните любое предложение слева — ' +
    'здесь появится разбор его веса: Posd, Posp, Score и вклад отдельных слов.</div>';
}

function showSentence(index) {
  const d = state.data;
  const s = d.sentences.find((x) => x.index === index);
  if (!s) return;
  state.currentSentence = index;
  $$('#heattext .sent').forEach((el) => el.classList.toggle('current', +el.dataset.i === index));
  const chosen = d.summary.indices.includes(index);
  const rank = [...d.sentences].sort((a, b) => b.weight - a.weight).findIndex((x) => x.index === index) + 1;
  const alpha = d.params.alpha, beta = d.params.beta;
  $('#sent-detail').innerHTML = `
    <div style="font-family:'PT Serif',Georgia,serif;margin-bottom:.6rem">${esc(s.text)}</div>
    <div class="formula">
      W = <span class="num">${fmt(s.weight, 3)}</span><br>
      Posd = 1 − BD/|D| = <span class="num">${fmt(s.posd, 3)}</span>${
        alpha === 1 ? '' : ` → ^${alpha} = <span class="num">${fmt(Math.pow(s.posd, alpha), 3)}</span>`}<br>
      Posp = 1 − BP/|P| = <span class="num">${fmt(s.posp, 3)}</span>${
        beta === 1 ? '' : ` → ^${beta} = <span class="num">${fmt(Math.pow(s.posp, beta), 3)}</span>`}<br>
      Score = Σ tf·w = <span class="num">${fmt(s.score, 3)}</span>${
        d.params.length_norm === 'none' ? '' : ' (с нормировкой по длине)'}
    </div>
    <div class="hint" style="margin:.5rem 0">Ранг по весу: <b>${rank}</b> из ${d.sentences.length};
      абзац №${s.paragraph + 1}; ${chosen ? '<b style="color:var(--ok)">входит в реферат</b>'
        : 'в реферат не вошло'}.</div>
    <div style="font-size:12px;color:var(--muted);margin-bottom:.2rem">Наибольший вклад в Score:</div>
    <table class="grid"><tr><th class="l">слово</th><th>tf</th><th>w</th><th>tf·w</th></tr>
      ${s.top_terms.map((t) => `<tr><td class="l">${esc(t.form)}</td><td>${t.tf}</td>
        <td>${fmt(t.w, 2)}</td><td><b>${fmt(t.contribution, 2)}</b></td></tr>`).join('')}
    </table>`;
}

/* ------------------- навигация «слово → предложения» ------------------- */
function focusTerm(term) {
  state.focusTerm = term;
  showTab('heat');
  history.replaceState(null, '', '#heat:term=' + encodeURIComponent(term));
  applyTermFocus(true);
}

function clearTermFocus() {
  state.focusTerm = null;
  history.replaceState(null, '', '#heat');
  applyTermFocus();
}

function applyTermFocus(scrollToFirst = false) {
  const banner = $('#term-banner');
  const container = $('#heattext');
  if (!state.data) return;
  if (!state.focusTerm) {
    container.classList.remove('focused');
    $$('#heattext .sent').forEach((el) => el.classList.remove('hit'));
    banner.hidden = true;
    return;
  }
  const term = state.focusTerm;
  const hits = state.data.sentences.filter((s) => (s.term_list || []).includes(term));
  const inSummary = hits.filter((s) => state.data.summary.indices.includes(s.index)).length;
  const weight = state.data.terms.find((t) => t.term === term);

  container.classList.add('focused');
  const hitSet = new Set(hits.map((s) => s.index));
  $$('#heattext .sent').forEach((el) => el.classList.toggle('hit', hitSet.has(+el.dataset.i)));

  banner.hidden = false;
  banner.innerHTML =
    `Термин <b>«${esc(weight ? weight.form : term)}»</b> (основа <code>${esc(term)}</code>${
      weight ? `, w = ${fmt(weight.weight, 3)}, tf = ${weight.tf}, df = ${weight.df}` : ''}):
     встречается в <b>${hits.length}</b> предложениях, из них <b>${inSummary}</b> вошли в реферат.
     <button class="btn ghost small" id="term-prev">← предыдущее</button>
     <button class="btn ghost small" id="term-next">следующее →</button>
     <button class="btn ghost small" id="term-clear">снять выделение (Esc)</button>`;

  let position = 0;
  const jump = (step) => {
    if (!hits.length) return;
    position = (position + step + hits.length) % hits.length;
    const target = $(`#heattext .sent[data-i="${hits[position].index}"]`);
    if (target) target.scrollIntoView({ block: 'center', behavior: 'smooth' });
    showSentence(hits[position].index);
  };
  $('#term-prev').onclick = () => jump(-1);
  $('#term-next').onclick = () => jump(1);
  $('#term-clear').onclick = clearTermFocus;
  if (scrollToFirst && hits.length) jump(0);
}

/* ---------------------------- веса терминов ----------------------------- */
function renderTerms() {
  const d = state.data;
  const maxKw = d.keywords.length ? d.keywords[0].weight : 1;
  $('#cloud').innerHTML = d.keywords.map((k) => {
    const size = 11 + 22 * Math.pow(k.weight / maxKw, 1.6);
    const opacity = 0.45 + 0.55 * k.weight / maxKw;
    return `<button class="cloudword" data-term="${esc(k.term)}"
      style="font-size:${size.toFixed(1)}px;color:rgba(47,93,140,${opacity.toFixed(2)});
      font-weight:${k.weight > maxKw * 0.7 ? 700 : 500};margin:.1rem .45rem;
      background:none;border:0;cursor:pointer;padding:0"
      title="w=${fmt(k.weight, 3)}; tf=${k.tf}; df=${k.df} — щёлкните, чтобы найти в тексте"
      >${esc(k.form)}</button>`;
  }).join('');
  $$('#cloud .cloudword').forEach((el) => { el.onclick = () => focusTerm(el.dataset.term); });
  drawTermsTable();
}

function drawTermsTable() {
  const d = state.data;
  const filter = ($('#term-filter').value || '').toLowerCase().trim();
  const rows = (d.terms || []).filter((t) => !filter || t.form.includes(filter) || t.term.includes(filter));
  const { key, dir } = state.termSort;
  rows.sort((a, b) => (a[key] > b[key] ? 1 : a[key] < b[key] ? -1 : 0) * dir);
  const shown = rows.slice(0, 200);
  const maxWeight = Math.max(...rows.map((r) => r.weight), 1e-9);
  const head = [['form', 'словоформа', 'l'], ['term', 'основа', 'l'], ['tf', 'tf'],
    ['tf_norm', 'tf/tf max'], ['df', 'df'], ['idf', 'IDF'], ['weight', 'w(t,D)']];
  $('#terms-table').innerHTML =
    `<tr>${head.map(([k, label, cls]) =>
      `<th class="${cls || ''}" data-key="${k}">${label}${key === k ? (dir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('')}<th>вес</th></tr>` +
    shown.map((t) => `<tr class="termrow" data-term="${esc(t.term)}" title="щёлкните, чтобы найти слово в тексте">
      <td class="l">${esc(t.form)}</td><td class="l" style="color:var(--muted)">${esc(t.term)}</td>
      <td>${t.tf}</td><td>${fmt(t.tf_norm, 3)}</td><td>${t.df}</td><td>${fmt(t.idf, 3)}</td>
      <td><b>${fmt(t.weight, 4)}</b></td>
      <td class="bar"><span class="b" style="width:${(t.weight / maxWeight * 100).toFixed(1)}%"></span></td></tr>`).join('');
  $('#term-count').textContent =
    `показано ${shown.length} из ${rows.length} (сервер присылает до 400 самых весомых; ` +
    `всего в документе ${d.document.terms} терминов)`;
  $$('#terms-table th[data-key]').forEach((th) => {
    th.onclick = () => {
      const k = th.dataset.key;
      state.termSort = { key: k, dir: state.termSort.key === k ? -state.termSort.dir : -1 };
      drawTermsTable();
    };
  });
  $$('#terms-table .termrow').forEach((tr) => {
    tr.onclick = () => focusTerm(tr.dataset.term);
  });
}

/* --------------------------- семантическая сеть -------------------------- */
const NODE_STYLE = {
  document: { color: '#2f5d8c', r: 20 },
  class: { color: '#7a5ea8', r: 12 },
  abstract: { color: '#7a5ea8', r: 15 },
  method: { color: '#96a2b3', r: 10 },
  attribute: { color: '#96a2b3', r: 10 },
  sentence: { color: '#b8562f', r: 9 },
  keyword: { color: '#2e7d5b', r: 8 },
};

function renderGraph(graphData) {
  const svg = $('#graph');
  const graph = graphData || state.graphData || state.data.graph;
  state.graphData = graph;
  svg.style.height = (graph.nodes.length > 45 ? 820 : 620) + 'px';
  const box = svg.parentElement.getBoundingClientRect();
  const width = Math.max(360, Math.round(box.width) || svg.clientWidth || 900);
  const height = Math.max(320, svg.clientHeight || 620);

  const nodes = graph.nodes.map((n) => ({
    ...n,
    x: width / 2 + (Math.random() - 0.5) * width * 0.6,
    y: height / 2 + (Math.random() - 0.5) * height * 0.6,
    vx: 0, vy: 0,
    r: NODE_STYLE[n.type] ? NODE_STYLE[n.type].r : 9,
  }));
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const links = graph.edges.filter((e) => byId[e.source] && byId[e.target])
    .map((e) => ({ ...e, s: byId[e.source], t: byId[e.target] }));

  svg.innerHTML = `<g id="g-view">
    <g id="g-edges" stroke-width="1.2"></g>
    <g id="g-elabels"></g>
    <g id="g-nodes"></g></g>`;
  const view = svg.querySelector('#g-view');
  const gEdges = svg.querySelector('#g-edges');
  const gLabels = svg.querySelector('#g-elabels');
  const gNodes = svg.querySelector('#g-nodes');
  const NS = 'http://www.w3.org/2000/svg';

  links.forEach((l) => {
    l.el = document.createElementNS(NS, 'line');
    l.el.setAttribute('class', 'edge');
    if (l.similarity !== undefined) {
      l.el.setAttribute('stroke-dasharray', '4 3');
      l.el.setAttribute('stroke', '#2e7d5b');
      l.el.setAttribute('stroke-width', (0.8 + 8 * l.similarity).toFixed(2));
    }
    gEdges.appendChild(l.el);
    l.labelEl = document.createElementNS(NS, 'text');
    l.labelEl.setAttribute('class', 'edge-label');
    l.labelEl.setAttribute('text-anchor', 'middle');
    l.labelEl.textContent = l.label;
    gLabels.appendChild(l.labelEl);
  });

  nodes.forEach((n) => {
    const style = NODE_STYLE[n.type] || { color: '#7a8798' };
    const g = document.createElementNS(NS, 'g');
    g.setAttribute('class', 'node');
    const circle = document.createElementNS(NS, 'circle');
    circle.setAttribute('r', n.r);
    circle.setAttribute('fill', style.color);
    circle.setAttribute('fill-opacity', n.type === 'sentence' || n.type === 'keyword' ? 0.85 : 1);
    circle.setAttribute('stroke', '#fff');
    circle.setAttribute('stroke-width', 1.5);
    const title = document.createElementNS(NS, 'title');
    title.textContent = `${n.id}\n${n.label}\n${n.note || ''}`;
    circle.appendChild(title);
    const text = document.createElementNS(NS, 'text');
    text.textContent = n.label.length > 26 ? n.label.slice(0, 26) + '…' : n.label;
    text.setAttribute('y', 4);
    text.setAttribute('fill', '#2b3444');
    n.textEl = text;                       // сторона подписи зависит от положения узла
    g.appendChild(circle); g.appendChild(text);
    gNodes.appendChild(g);
    n.el = g;

    g.addEventListener('mousedown', (event) => {
      event.stopPropagation();
      n.fixed = true;
      const move = (e) => {
        const point = toLocal(svg, e);
        n.x = point.x; n.y = point.y; n.vx = n.vy = 0;
        tickDraw();
      };
      const up = () => { n.fixed = false; document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); };
      document.addEventListener('mousemove', move);
      document.addEventListener('mouseup', up);
    });
  });

  // ------------------------- раскладка графа -------------------------
  // Семантическая сеть документа — дерево с корнем-документом, поэтому
  // применяется радиальная древовидная раскладка: узел документа в центре,
  // отношения первого уровня по окружности, предложения и ключевые слова —
  // секторами вокруг своих множеств. Для сети всей коллекции используется
  // двухкольцевая раскладка: документы на внутреннем кольце, ключевые слова —
  // на внешнем, рядом со «своими» документами (общие слова оказываются между
  // связанными документами).
  const adjacency = new Map(nodes.map((n) => [n.id, []]));
  links.forEach((l) => {
    adjacency.get(l.s.id).push(l.t.id);
    adjacency.get(l.t.id).push(l.s.id);
  });

  const documents = nodes.filter((n) => n.type === 'document');
  const rotate = state.graphRotate || 0;      // поворот всей раскладки
  const cx = width / 2, cy = height / 2;
  const radius = Math.min(width * 0.44, height * 0.44);

  if (documents.length > 1) layoutCollection(); else layoutTree();

  function layoutCollection() {
    const inner = radius * 0.42, outer = radius * 0.95;
    const angleOf = new Map();
    documents.forEach((d, i) => {
      const angle = rotate - Math.PI / 2 + 2 * Math.PI * i / documents.length;
      angleOf.set(d.id, angle);
      d.x = cx + inner * Math.cos(angle);
      d.y = cy + inner * Math.sin(angle);
    });
    // служебные узлы (предметные области) — в центре
    const central = nodes.filter((n) => n.type === 'class' || n.type === 'attribute');
    central.forEach((n, i) => {
      const angle = 2 * Math.PI * i / Math.max(1, central.length);
      n.x = cx + radius * 0.13 * Math.cos(angle);
      n.y = cy + radius * 0.13 * Math.sin(angle);
    });
    // ключевые слова: средний угол связанных с ними документов
    const keywords = nodes.filter((n) => n.type === 'keyword');
    keywords.forEach((n) => {
      let sx = 0, sy = 0, count = 0;
      adjacency.get(n.id).forEach((id) => {
        if (!angleOf.has(id)) return;
        sx += Math.cos(angleOf.get(id)); sy += Math.sin(angleOf.get(id)); count++;
      });
      n.angle = count ? Math.atan2(sy / count, sx / count) : Math.random() * 2 * Math.PI;
      n.shared = count > 1;
    });
    // равномерно разносим по углу, чтобы подписи не накладывались
    keywords.sort((a, b) => a.angle - b.angle);
    const stepAngle = 2 * Math.PI / Math.max(1, keywords.length);
    keywords.forEach((n, i) => {
      const angle = -Math.PI + i * stepAngle + stepAngle / 2;
      const r = n.shared ? outer * 0.78 : outer;
      n.x = cx + r * Math.cos(angle) * 1.12;
      n.y = cy + r * Math.sin(angle) * 0.92;
    });
  }

  function layoutTree() {
    const root = documents[0] || nodes[0];
    const depth = new Map([[root.id, 0]]);
    const parent = new Map();
    const order = [root.id];
    for (let i = 0; i < order.length; i++) {
      const id = order[i];
      adjacency.get(id).forEach((next) => {
        if (depth.has(next)) return;
        depth.set(next, depth.get(id) + 1);
        parent.set(next, id);
        order.push(next);
      });
    }
    const children = new Map(nodes.map((n) => [n.id, []]));
    parent.forEach((up, down) => children.get(up).push(down));

    // ширина поддерева в «листьях» определяет размер углового сектора
    const leaves = new Map();
    const countLeaves = (id) => {
      const kids = children.get(id);
      const total = kids.length ? kids.reduce((sum, k) => sum + countLeaves(k), 0) : 2.2;
      leaves.set(id, total);
      return total;
    };
    countLeaves(root.id);

    const byId = new Map(nodes.map((n) => [n.id, n]));
    const maxDepth = Math.max(1, ...depth.values());
    const stagger = [0.62, 0.88, 1.10];          // «ступеньки» радиуса для одиночных узлов
    let staggerIndex = 0;
    const place = (id, from, to) => {
      const node = byId.get(id);
      const level = depth.get(id);
      const angle = (from + to) / 2;
      if (level === 0) { node.x = cx; node.y = cy; }
      else {
        const compact = level === 1 && children.get(id).length === 0
          ? stagger[staggerIndex++ % stagger.length] : 1;
        const r = radius * (level / maxDepth) * 0.92 * compact;
        node.x = cx + r * Math.cos(angle) * 1.15;
        node.y = cy + r * Math.sin(angle) * 0.95;
      }
      let cursor = from;
      children.get(id).forEach((kid) => {
        const share = (to - from) * leaves.get(kid) / Math.max(1, leaves.get(id));
        place(kid, cursor, cursor + share);
        cursor += share;
      });
    };
    place(root.id, rotate - Math.PI * 1.5, rotate + Math.PI * 0.5);

    // узлы, не связанные с корнем, выносим в нижний ряд
    let stray = 0;
    nodes.forEach((n) => {
      if (depth.has(n.id)) return;
      n.x = 60 + (stray++) * 140;
      n.y = height - 30;
    });
  }

  function tickDraw() {
    links.forEach((l) => {
      l.el.setAttribute('x1', l.s.x); l.el.setAttribute('y1', l.s.y);
      l.el.setAttribute('x2', l.t.x); l.el.setAttribute('y2', l.t.y);
      l.labelEl.setAttribute('x', (l.s.x + l.t.x) / 2);
      l.labelEl.setAttribute('y', (l.s.y + l.t.y) / 2 - 3);
    });
    nodes.forEach((n) => {
      n.el.setAttribute('transform', `translate(${n.x},${n.y})`);
      if (!n.textEl) return;
      const toLeft = n.x < width / 2 - 20;       // подпись наружу от центра схемы
      n.textEl.setAttribute('x', toLeft ? -(n.r + 5) : n.r + 5);
      n.textEl.setAttribute('text-anchor', toLeft ? 'end' : 'start');
    });
  }

  tickDraw();

  // масштабирование и панорамирование
  let scale = 1, tx = 0, ty = 0;
  const apply = () => view.setAttribute('transform', `translate(${tx},${ty}) scale(${scale})`);

  function fitView() {
    const pad = 24;
    const xs = nodes.map((n) => n.x), ys = nodes.map((n) => n.y);
    const minX = Math.min(...xs) - 130, maxX = Math.max(...xs) + 130;  // запас на подписи
    const minY = Math.min(...ys) - 24, maxY = Math.max(...ys) + 24;
    const boxWidth = Math.max(1, maxX - minX), boxHeight = Math.max(1, maxY - minY);
    scale = Math.max(0.3, Math.min(1.6, Math.min((width - 2 * pad) / boxWidth,
                                                 (height - 2 * pad) / boxHeight)));
    tx = pad - minX * scale + Math.max(0, (width - 2 * pad - boxWidth * scale) / 2);
    ty = pad - minY * scale + Math.max(0, (height - 2 * pad - boxHeight * scale) / 2);
    apply();
  }
  svg.onwheel = (event) => {
    event.preventDefault();
    const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12;
    scale = Math.max(0.3, Math.min(3, scale * factor));
    apply();
  };
  svg.onmousedown = (event) => {
    const start = { x: event.clientX - tx, y: event.clientY - ty };
    const move = (e) => { tx = e.clientX - start.x; ty = e.clientY - start.y; apply(); };
    const up = () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); };
    document.addEventListener('mousemove', move);
    document.addEventListener('mouseup', up);
  };
  $('#g-fit').onclick = () => fitView();
  fitView();                            // сразу вписываем готовую раскладку в кадр
  $('#g-relayout').onclick = () => { state.graphRotate = (state.graphRotate || 0) + 0.6; renderGraph(graph); };
  $('#g-labels').onchange = (event) => { gLabels.style.display = event.target.checked ? '' : 'none'; };
  if (graph.nodes.length > 45 && $('#g-labels').checked) $('#g-labels').checked = false;
  gLabels.style.display = $('#g-labels').checked ? '' : 'none';
}

function toLocal(svg, event) {
  const rect = svg.getBoundingClientRect();
  const view = svg.querySelector('#g-view');
  const transform = view.getAttribute('transform') || '';
  const m = /translate\(([-\d.]+),([-\d.]+)\) scale\(([-\d.]+)\)/.exec(transform);
  const tx = m ? +m[1] : 0, ty = m ? +m[2] : 0, scale = m ? +m[3] : 1;
  return { x: (event.clientX - rect.left - tx) / scale, y: (event.clientY - rect.top - ty) / scale };
}

function renderScs(code) {
  code = code || (state.graphScope === 'collection' && state.collectionGraph
    ? state.collectionGraph.scs : state.data.scs);
  state.scsShown = code;
  const highlighted = esc(code)
    .replace(/(\/\/[^\n]*)/g, '<span class="c">$1</span>')
    .replace(/(\[[^\]\n]*\])/g, '<span class="s">$1</span>')
    .replace(/\b(nrel_[a-z_]+|rrel_\d+|concept_[a-z_]+)\b/g, '<span class="k">$1</span>');
  $('#scs-code').innerHTML = highlighted;
}

/* ---------------------------- сравнение методов -------------------------- */
function renderCompare() {
  const d = state.data, q = d.quality;
  const order = ['tfidf', 'textrank', 'hybrid', 'lead'];
  const rows = order.map((name) => {
    const method = d.methods[name];
    const comparison = q.comparisons[name];
    const current = name === d.params.method;
    return `<tr${current ? ' style="background:#f3f8ff"' : ''}>
      <td class="l">${esc(method.title)}${current ? ' <span class="pill">выбран</span>' : ''}</td>
      <td>${method.indices.length}</td>
      <td>${method.indices.map((i) => i + 1).join(', ')}</td>
      <td>${comparison ? fmt(comparison.agreement, 2) : '—'}</td>
      <td>${comparison ? fmt(comparison.rouge1.f1, 3) : '—'}</td>
      <td>${comparison ? fmt(comparison.rouge2.f1, 3) : '—'}</td>
      <td>${comparison ? fmt(comparison.rougeL.f1, 3) : '—'}</td>
      <td>${fmt(method.elapsed_ms, 2)}</td></tr>`;
  }).join('');
  $('#cmp-table').innerHTML =
    `<tr><th class="l">метод</th><th>N</th><th>номера предложений</th>
      <th title="доля совпавших предложений">Жаккар</th>
      <th title="совпадение по отдельным словам">ROUGE‑1 F</th>
      <th title="совпадение по парам слов">ROUGE‑2 F</th>
      <th title="наибольшая общая подпоследовательность">ROUGE‑L F</th><th>мс</th></tr>` + rows;

  const bias = q.position_bias;
  const plots = order.map((name) => {
    const marks = d.methods[name].indices.map((i) => {
      const s = d.sentences.find((x) => x.index === i);
      return `<i style="left:${(s.start / d.document.chars * 100).toFixed(2)}%" title="предложение №${i + 1}"></i>`;
    }).join('');
    return `<div style="margin-bottom:.5rem">
      <div class="hint">${esc(d.methods[name].title)}</div>
      <div class="posplot">${marks}<span style="left:2px">начало</span>
        <span style="right:2px">конец документа</span></div></div>`;
  }).join('');

  const kept = bias.content_top_kept, total = bias.content_top_total;
  $('#bias-body').innerHTML = `
    ${plots}
    <div class="stats" style="margin:.6rem 0">
      <div class="stat"><div class="v">${(bias.mean_relative_position * 100).toFixed(1)}%</div>
        <div class="k">среднее положение отобранных предложений</div></div>
      <div class="stat"><div class="v">${kept} / ${total}</div>
        <div class="k">самых содержательных предложений (по Score) попало в реферат</div></div>
      <div class="stat"><div class="v">${bias.last_third_selected}</div>
        <div class="k">предложений из последней трети документа</div></div>
    </div>
    <div class="note ${kept >= total * 0.8 ? 'ok' : ''}">
      Множители Posd и Posp перемножаются со Score, поэтому предложение из конца документа
      получает Posd ≈ 0 и не попадает в реферат, каким бы содержательным оно ни было.
      ${kept < total
        ? `Здесь ${total - kept} из ${total} наиболее насыщенных терминами предложений отсеяны именно позицией.`
        : 'В этом документе содержательные предложения сосредоточены в начале, перекос не проявился.'}
      Уменьшите α до 0 в исследовательских параметрах, чтобы увидеть реферат без учёта позиции.</div>`;

  $('#cmp-cols').innerHTML = order.slice(0, 3).map((name) => `
    <div><div class="hint" style="margin-bottom:.3rem"><b>${esc(d.methods[name].title)}</b></div>
      <div class="plain" style="font-size:13.5px">${esc(d.methods[name].text)}</div></div>`).join('');
}

/* ------------------- семантическая сеть и близость коллекции ------------------- */
async function loadCollectionGraph(force = false) {
  if (state.collectionGraph && !force) return state.collectionGraph;
  busy(true);
  try {
    state.collectionGraph = await api('/api/collection_graph',
      { ...params(), keywords_per_document: 6 });
    return state.collectionGraph;
  } finally {
    busy(false);
  }
}

function drawSimilarity() {
  const data = state.collectionGraph;
  if (!data || !data.similarity) return;
  const { titles, matrix } = data.similarity;
  const short = titles.map((t) => (t.length > 18 ? t.slice(0, 17) + '…' : t));
  const head = `<tr><th class="l">документ</th>${short.map((t) => `<th>${esc(t)}</th>`).join('')}</tr>`;
  const rows = matrix.map((row, i) => `<tr><td class="l">${esc(titles[i])}</td>` +
    row.map((value, j) => {
      if (i === j) return '<td style="color:#c3ccd8">—</td>';
      const alpha = Math.min(1, value / 0.2);
      return `<td style="background:rgba(46,125,91,${(alpha * 0.55).toFixed(2)})">${value.toFixed(3)}</td>`;
    }).join('') + '</tr>').join('');
  $('#sim-table').innerHTML = head + rows;
  $('#sim-info').innerHTML = `Расчёт занял ${fmt(data.elapsed_ms, 0)} мс. Наиболее близкая пара: ` +
    `<b>${esc(data.pairs[0] ? data.pairs[0].a + ' ↔ ' + data.pairs[0].b : '—')}</b>` +
    (data.pairs[0] ? ` (${fmt(data.pairs[0].score, 3)})` : '');
}

/* ------------------------------- коллекция ------------------------------- */
async function runBatch() {
  const info = $('#batch-info');
  info.innerHTML = '<span class="spinner dark"></span> обработка…';
  busy(true);
  try {
    const data = await api('/api/batch', params());
    state.batchRows = data.rows;
    info.textContent = `${data.rows.length} документов за ${fmt(data.total_time_ms, 0)} мс ` +
      `(в среднем ${fmt(data.total_time_ms / data.rows.length, 1)} мс на документ)`;
    drawBatch();
    loadCollectionGraph().then(drawSimilarity).catch(() => {});
  } catch (error) {
    info.textContent = 'Ошибка: ' + error.message;
  } finally {
    busy(false);
  }
}

function drawBatch() {
  if (!state.batchRows) return;
  const { key, dir } = state.batchSort;
  const rows = [...state.batchRows].sort((a, b) => (a[key] > b[key] ? 1 : a[key] < b[key] ? -1 : 0) * dir);
  const head = [['title', 'документ', 'l'], ['language', 'яз.'], ['domain', 'область', 'l'],
    ['chars', 'симв.'], ['sentences', 'предл.'], ['terms', 'терминов'], ['time_ms', 'время, мс'],
    ['compression', 'сжатие'], ['keyword_coverage', 'покрытие'], ['mean_position', 'ср. позиция'],
    ['content_top_kept', 'топ‑Score в реферате'], ['agreement_textrank', 'Жаккар с TextRank'],
    ['rouge1_textrank', 'ROUGE‑1']];
  $('#batch-table').innerHTML =
    `<tr>${head.map(([k, label, cls]) => `<th class="${cls || ''}" data-key="${k}">${label}${key === k ? (dir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('')}
      <th class="l">топ‑5 ключевых слов</th></tr>` +
    rows.map((r) => `<tr class="batchrow" data-id="${esc(r.id)}" title="открыть документ">
      <td class="l">${esc(r.title)}</td><td>${r.language}</td><td class="l">${esc(r.domain)}</td>
      <td>${num(r.chars)}</td><td>${r.sentences}</td><td>${num(r.terms)}</td><td>${fmt(r.time_ms, 1)}</td>
      <td>${(r.compression * 100).toFixed(1)}%</td><td>${(r.keyword_coverage * 100).toFixed(0)}%</td>
      <td>${(r.mean_position * 100).toFixed(0)}%</td><td>${r.content_top_kept}</td>
      <td>${fmt(r.agreement_textrank, 2)}</td><td>${fmt(r.rouge1_textrank, 3)}</td>
      <td class="l" style="color:var(--muted)">${esc(r.keywords.join(', '))}</td></tr>`).join('');
  $$('#batch-table th[data-key]').forEach((th) => {
    th.onclick = () => {
      const k = th.dataset.key;
      state.batchSort = { key: k, dir: state.batchSort.key === k ? -state.batchSort.dir : -1 };
      drawBatch();
    };
  });
  $$('#batch-table .batchrow').forEach((tr) => {
    tr.onclick = () => { selectDocument(tr.dataset.id); showTab('abstract'); };
  });
}

function tableCsv(rows, name) {
  if (!rows || !rows.length) { toast('Нет данных для выгрузки'); return; }
  const columns = Object.keys(rows[0]);
  const lines = [columns.join(';')].concat(rows.map((r) =>
    columns.map((c) => Array.isArray(r[c]) ? r[c].join(' ') : r[c]).join(';')));
  download(name, lines.join('\n'), 'text/csv;charset=utf-8');
}

/* ------------------------- статистика коллекции ------------------------- */
async function loadStats(force = false) {
  if (state.stats && !force) { renderStats(); return; }
  busy(true);
  try {
    state.stats = await api('/api/stats');
    renderStats();
  } catch (error) {
    toast('Не удалось получить статистику: ' + error.message, 5000);
  } finally {
    busy(false);
  }
}

function renderStats() {
  const st = state.stats;
  if (!st) return;

  const tiles = [
    ['документов', st.size], ['символов', num(st.totals.chars)],
    ['слов', num(st.totals.words)], ['значимых слов', num(st.filtering.kept)],
    ['предложений', num(st.totals.sentences)], ['абзацев', num(st.totals.paragraphs)],
    ['уникальных терминов', num(st.unique_terms)],
    ['терминов с весом 0', num(st.zero_weight_terms)],
    ['расчёт, мс', fmt(st.elapsed_ms, 0)],
  ];
  $('#st-totals').innerHTML = tiles.map(([k, v]) =>
    `<div class="stat"><div class="v">${v}</div><div class="k">${k}</div></div>`).join('');
  $('#st-note').innerHTML =
    `Вес обнуляется у терминов с df = |DB| = ${st.size}: они встречаются во всех документах.
     Сейчас таких терминов <b>${st.zero_weight_terms}</b> — коллекция двуязычная, и ни одна
     основа не может встретиться одновременно в русских и английских текстах,
     поэтому df никогда не достигает ${st.size}.`;

  // --- разбор отсева слов
  const f = st.filtering;
  const parts = [
    ['значимые слова', f.kept, '#2f5d8c'],
    ['стоп-слова', f.stopwords, '#b8562f'],
    ['короче 3 букв', f.short, '#7a5ea8'],
    ['чужой алфавит', f.foreign, '#2e7d5b'],
  ];
  const totalWords = f.words || 1;
  $('#st-filter').innerHTML = `
    <div class="stackbar">${parts.map(([label, value, color]) => {
      const share = value / totalWords * 100;
      return `<div style="width:${share}%;background:${color}" title="${label}: ${num(value)} (${share.toFixed(1)}%)">${
        share > 7 ? share.toFixed(0) + '%' : ''}</div>`;
    }).join('')}</div>
    <div class="stacklegend">${parts.map(([label, value, color]) =>
      `<span><i style="background:${color}"></i>${label}: <b>${num(value)}</b>
        (${(value / totalWords * 100).toFixed(1)}%)</span>`).join('')}
      <span style="color:var(--muted)">кроме того, чисел в текстах: <b>${num(f.numbers)}</b></span>
    </div>
    <div class="hint" style="margin-top:.5rem">Всего словоформ в коллекции: ${num(f.words)}.
      После фильтрации и стемминга остаётся ${num(f.kept)} значимых слов —
      именно они участвуют в расчёте tf и df.</div>`;

  $('#st-zipf').innerHTML = zipfChart(st.zipf);
  $('#st-df').innerHTML = dfChart(st.df_histogram, st.size);
  drawStatsTable();
}

function zipfChart(zipf) {
  const width = 460, height = 300, pad = { l: 46, r: 12, t: 12, b: 34 };
  const colors = { ru: '#2f5d8c', en: '#b8562f' };
  const languages = Object.keys(zipf).filter((l) => zipf[l].points.length);
  if (!languages.length) return '<div class="hint">Недостаточно данных.</div>';

  const maxLogRank = Math.max(...languages.map((l) =>
    Math.log10(zipf[l].points[zipf[l].points.length - 1].rank)));
  const maxLogFreq = Math.max(...languages.map((l) => Math.log10(zipf[l].points[0].freq)));
  const x = (rank) => pad.l + Math.log10(rank) / (maxLogRank || 1) * (width - pad.l - pad.r);
  const y = (freq) => height - pad.b - Math.log10(freq) / (maxLogFreq || 1) * (height - pad.t - pad.b);

  let svg = `<svg viewBox="0 0 ${width} ${height}" class="chart">`;
  for (let p = 0; p <= Math.ceil(maxLogFreq); p++) {
    const yy = y(Math.pow(10, p));
    svg += `<line class="grid-line" x1="${pad.l}" y1="${yy}" x2="${width - pad.r}" y2="${yy}"/>
            <text x="${pad.l - 6}" y="${yy + 3}" text-anchor="end">10${p ? '^' + p : '⁰'}</text>`;
  }
  for (let p = 0; p <= Math.ceil(maxLogRank); p++) {
    const xx = x(Math.pow(10, p));
    svg += `<line class="grid-line" x1="${xx}" y1="${pad.t}" x2="${xx}" y2="${height - pad.b}"/>
            <text x="${xx}" y="${height - pad.b + 14}" text-anchor="middle">10${p ? '^' + p : '⁰'}</text>`;
  }
  svg += `<line class="axis" x1="${pad.l}" y1="${pad.t}" x2="${pad.l}" y2="${height - pad.b}"/>
          <line class="axis" x1="${pad.l}" y1="${height - pad.b}" x2="${width - pad.r}" y2="${height - pad.b}"/>
          <text x="${width / 2}" y="${height - 4}" text-anchor="middle">ранг термина (лог. шкала)</text>
          <text x="12" y="${height / 2}" text-anchor="middle" transform="rotate(-90 12 ${height / 2})">частота</text>`;

  languages.forEach((lang) => {
    const data = zipf[lang];
    svg += data.points.map((p) =>
      `<circle class="dot" cx="${x(p.rank).toFixed(1)}" cy="${y(p.freq).toFixed(1)}" r="2.4"
        fill="${colors[lang] || '#555'}"><title>ранг ${p.rank}, частота ${p.freq}</title></circle>`).join('');
    const first = data.points[0];
    const lastRank = data.points[data.points.length - 1].rank;
    const fit = (rank) => first.freq * Math.pow(rank, -data.exponent);
    svg += `<path class="fit" stroke="${colors[lang] || '#555'}"
      d="M ${x(1)} ${y(fit(1))} L ${x(lastRank)} ${y(Math.max(1, fit(lastRank)))}"/>`;
  });

  svg += '</svg>';
  const legend = languages.map((lang) =>
    `<span><i style="background:${colors[lang]};display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:.35rem"></i>
      ${lang === 'ru' ? 'русские' : 'английские'} тексты: показатель s = <b>${zipf[lang].exponent}</b>,
      терминов ${num(zipf[lang].total_terms)}, встречается один раз — ${num(zipf[lang].hapax)}</span>`).join('');
  return svg + `<div class="stacklegend">${legend}</div>
    <div class="hint" style="margin-top:.4rem">Точки ложатся на прямую в логарифмических
      координатах — частоты подчиняются закону Ципфа f(r) ≈ C/r<sup>s</sup>. Пунктир — аппроксимация
      методом наименьших квадратов. Большое число слов, встретившихся один раз, объясняет,
      почему IDF так сильно поднимает вес редких терминов.</div>`;
}

function dfChart(histogram, size) {
  const width = 460, height = 300, pad = { l: 46, r: 12, t: 12, b: 34 };
  const maxTerms = Math.max(...histogram.map((r) => r.terms), 1);
  const barWidth = (width - pad.l - pad.r) / histogram.length;
  let svg = `<svg viewBox="0 0 ${width} ${height}" class="chart">`;
  for (let i = 0; i <= 4; i++) {
    const value = maxTerms * i / 4;
    const yy = height - pad.b - (height - pad.t - pad.b) * i / 4;
    svg += `<line class="grid-line" x1="${pad.l}" y1="${yy}" x2="${width - pad.r}" y2="${yy}"/>
            <text x="${pad.l - 6}" y="${yy + 3}" text-anchor="end">${Math.round(value)}</text>`;
  }
  histogram.forEach((row, i) => {
    const barHeight = (height - pad.t - pad.b) * row.terms / maxTerms;
    const xx = pad.l + i * barWidth + barWidth * 0.15;
    const yy = height - pad.b - barHeight;
    svg += `<rect class="bar${row.df === size ? ' zero' : ''}" x="${xx.toFixed(1)}" y="${yy.toFixed(1)}"
      width="${(barWidth * 0.7).toFixed(1)}" height="${Math.max(0, barHeight).toFixed(1)}">
      <title>df = ${row.df}: ${row.terms} терминов, IDF = ${row.idf}</title></rect>
      <text x="${(xx + barWidth * 0.35).toFixed(1)}" y="${height - pad.b + 14}" text-anchor="middle">${row.df}</text>`;
    if (row.terms > 0) {
      svg += `<text x="${(xx + barWidth * 0.35).toFixed(1)}" y="${(yy - 4).toFixed(1)}"
        text-anchor="middle" style="font-size:9px">${row.terms}</text>`;
    }
  });
  svg += `<line class="axis" x1="${pad.l}" y1="${pad.t}" x2="${pad.l}" y2="${height - pad.b}"/>
          <line class="axis" x1="${pad.l}" y1="${height - pad.b}" x2="${width - pad.r}" y2="${height - pad.b}"/>
          <text x="${width / 2}" y="${height - 4}" text-anchor="middle">df(t) — в скольких документах встречается термин</text>
          </svg>`;
  return svg + `<div class="hint" style="margin-top:.4rem">Чем меньше df, тем выше IDF = log(|DB|/df)
    и тем ценнее термин как примета документа. Столбец df = ${size} (отмечен другим цветом)
    соответствует IDF = 0: такие термины полностью исключаются из расчёта.</div>`;
}

function drawStatsTable() {
  const st = state.stats;
  const { key, dir } = state.statsSort;
  const rows = [...st.documents].sort((a, b) => (a[key] > b[key] ? 1 : a[key] < b[key] ? -1 : 0) * dir);
  const head = [['title', 'документ', 'l'], ['language', 'яз.'], ['domain', 'область', 'l'],
    ['chars', 'симв.'], ['words', 'слов'], ['kept', 'значимых'],
    ['stopword_share', 'доля стоп-слов'], ['paragraphs', 'абзацев'], ['sentences', 'предл.'],
    ['avg_sentence_chars', 'ср. длина предл.'], ['avg_paragraph_sentences', 'предл. в абзаце'],
    ['terms', 'терминов'], ['hapax', 'встретились 1 раз'], ['tf_max', 'tf max']];
  $('#st-table').innerHTML =
    `<tr>${head.map(([k, label, cls]) => `<th class="${cls || ''}" data-key="${k}">${label}${key === k ? (dir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('')}</tr>` +
    rows.map((r) => `<tr class="strow" data-id="${esc(r.id)}" title="открыть документ">
      <td class="l">${esc(r.title)}${r.added_by_user ? ' <span class="badge">свой</span>' : ''}</td>
      <td>${r.language}</td><td class="l">${esc(r.domain)}</td>
      <td>${num(r.chars)}</td><td>${num(r.words)}</td><td>${num(r.kept)}</td>
      <td>${(r.stopword_share * 100).toFixed(1)}%</td><td>${r.paragraphs}</td><td>${r.sentences}</td>
      <td>${r.avg_sentence_chars}</td><td>${r.avg_paragraph_sentences}</td>
      <td>${num(r.terms)}</td><td>${num(r.hapax)}</td><td>${r.tf_max}</td></tr>`).join('');
  $$('#st-table th[data-key]').forEach((th) => {
    th.onclick = () => {
      const k = th.dataset.key;
      state.statsSort = { key: k, dir: state.statsSort.key === k ? -state.statsSort.dir : -1 };
      drawStatsTable();
    };
  });
  $$('#st-table .strow').forEach((tr) => {
    tr.onclick = () => { selectDocument(tr.dataset.id); showTab('abstract'); };
  });
}

/* --------------------------------- экспорт -------------------------------- */
function download(name, content, type) {
  const blob = new Blob(['﻿' + content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

async function exportAs(format, scope) {
  busy(true);
  try {
    const body = requestBody({ format });
    if (scope === 'collection') body.scope = 'collection';
    const response = await fetch('/api/export', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.error || `HTTP ${response.status}`);
    }
    const text = await response.text();
    const name = scope === 'collection' ? 'collection.scs'
      : `${state.custom ? 'user_document' : state.docId}_abstract.${format}`;
    download(name, text, response.headers.get('Content-Type') || 'text/plain');
    toast('Сохранено: ' + name);
  } catch (error) {
    toast('Не удалось сохранить файл: ' + error.message, 5000);
  } finally {
    busy(false);
  }
}

/* --------------------------------- диалоги -------------------------------- */
function confirmDialog(title, text, onConfirm) {
  const dialog = $('#confirm-dialog');
  $('#confirm-title').textContent = title;
  $('#confirm-text').textContent = text;
  dialog.returnValue = '';
  dialog.showModal();
  dialog.onclose = () => { if (dialog.returnValue === 'ok') onConfirm(); };
}

async function loadFromUrl() {
  const input = $('#url-input');
  const errorBox = $('#url-error');
  const button = $('#url-load');
  const url = input.value.trim();
  errorBox.hidden = true;
  if (!/^https?:\/\/\S+$/i.test(url)) {
    errorBox.hidden = false;
    errorBox.textContent = 'Введите полный адрес страницы, например https://ru.wikipedia.org/wiki/…';
    return;
  }
  button.disabled = true;
  button.innerHTML = '<span class="spinner"></span> загрузка…';
  busy(true);
  try {
    const page = await api('/api/fetch_url', { url });
    $('#url-dialog').close();
    toast(`Загружено: «${page.title}» — ${num(page.chars)} символов`, 3000);
    await addTextToCollection({ title: page.title, text: page.text, source: page.url });
  } catch (error) {
    errorBox.hidden = false;
    errorBox.textContent = 'Не удалось загрузить: ' + error.message;
  } finally {
    button.disabled = false;
    button.textContent = 'Загрузить и реферировать';
    busy(false);
  }
}

/* ------------------------------- интерфейс -------------------------------- */
function buildTabs() {
  $('#tabs').innerHTML = TABS.map((tab, i) =>
    `<button data-tab="${tab.id}" role="tab"${i === 0 ? ' class="active"' : ''}>
       <span class="n">${i + 1}</span>${tab.label}</button>`).join('');
  $$('#tabs button').forEach((button) => {
    button.onclick = () => showTab(button.dataset.tab);
  });
}

function showTab(name) {
  if (!TABS.some((t) => t.id === name)) name = 'abstract';
  if (location.hash.slice(1).split(':')[0] !== name) history.replaceState(null, '', '#' + name);
  $$('#tabs button').forEach((b) => b.classList.toggle('active', b.dataset.tab === name));
  $$('section.tab').forEach((s) => s.classList.toggle('active', s.id === 'tab-' + name));
  $('#docbar').hidden = (name === 'batch' || name === 'stats' || name === 'help');
  if (name === 'graph' && state.data) {
    renderGraph(state.graphScope === 'collection' && state.collectionGraph
      ? state.collectionGraph.graph : state.data.graph);
  }
  if (name === 'batch' && !state.batchRows) runBatch();
  if (name === 'stats') loadStats();
  if (name === 'help') loadHelp();
}

async function loadHelp() {
  if (state.helpLoaded) return;
  try {
    const response = await fetch('help.html');
    $('#help-body').innerHTML = await response.text();
    state.helpLoaded = true;
  } catch {
    $('#help-body').textContent = 'Не удалось загрузить справку.';
  }
}

function syncSliderLabels() {
  $('#v-sent').textContent = $('#p-sent').value;
  $('#v-kw').textContent = $('#p-kw').value;
  $('#v-alpha').textContent = (+$('#p-alpha').value).toFixed(1);
  $('#v-beta').textContent = (+$('#p-beta').value).toFixed(1);
  $('#v-mmr').textContent = (+$('#p-mmr').value).toFixed(2);
}

function bindUi() {
  buildTabs();

  [['#p-sent', analyzeSoon], ['#p-kw', analyzeSoon], ['#p-alpha', analyzeSoon],
   ['#p-beta', analyzeSoon], ['#p-mmr', analyzeSoon]].forEach(([selector, handler]) => {
    $(selector).oninput = () => { syncSliderLabels(); markChangedParams(); handler(); };
  });
  ['#p-method', '#p-conflate', '#p-lennorm'].forEach((selector) => {
    $(selector).onchange = () => {
      markChangedParams();
      state.collectionGraph = null;
      state.batchRows = null;
      analyze();
    };
  });
  $('#btn-reset').onclick = resetParams;
  syncSliderLabels();

  $('#doc-search').oninput = debounce(renderDocList, 120);
  $('#term-filter').oninput = debounce(drawTermsTable, 150);

  $$('[data-export]').forEach((button) => {
    button.onclick = () => exportAs(button.dataset.export, button.dataset.scope);
  });
  $('#btn-print').onclick = () => window.print();
  $('#btn-help').onclick = () => showTab('help');
  $('#btn-keys').onclick = () => $('#keys-dialog').showModal();
  $('#btn-add-collection').onclick = addCurrentToCollection;
  $('#batch-run').onclick = runBatch;
  $('#batch-csv').onclick = () => tableCsv(state.batchRows, 'collection_report.csv');
  $('#st-csv').onclick = () => tableCsv(state.stats && state.stats.documents, 'collection_stats.csv');
  $('#sim-run').onclick = async () => {
    $('#sim-info').innerHTML = '<span class="spinner dark"></span> расчёт…';
    await loadCollectionGraph(true);
    drawSimilarity();
  };

  $('#g-scope').onchange = async (event) => {
    state.graphScope = event.target.value;
    if (state.graphScope === 'collection') {
      await loadCollectionGraph();
      renderGraph(state.collectionGraph.graph);
      renderScs(state.collectionGraph.scs);
      $('#scs-note').textContent = 'показана сеть всей коллекции';
    } else {
      renderGraph(state.data.graph);
      renderScs(state.data.scs);
      $('#scs-note').textContent = '';
    }
  };
  $('#scs-copy').onclick = async () => {
    try {
      await navigator.clipboard.writeText(state.scsShown || state.data.scs);
      toast('SC-код скопирован в буфер обмена');
    } catch {
      toast('Копирование недоступно — сохраните файл .scs');
    }
  };
  $('#scs-save').onclick = () =>
    exportAs('scs', state.graphScope === 'collection' ? 'collection' : undefined);

  // --- источники документов
  $('#btn-own').onclick = () => $('#own-dialog').showModal();
  $('#own-dialog').addEventListener('close', () => {
    if ($('#own-dialog').returnValue !== 'ok') return;
    const text = $('#own-text').value.trim();
    if (text.length < 400) {
      toast('Слишком короткий текст: для добавления в коллекцию нужно не менее 400 символов', 4000);
      return;
    }
    addTextToCollection({ title: $('#own-title').value.trim() || 'Документ пользователя', text });
  });
  $('#btn-file').onclick = () => $('#file').click();
  $('#file').onchange = async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    const text = await file.text();
    await addTextToCollection({
      title: file.name.replace(/\.txt$/i, ''), text, source: file.name,
    });
    event.target.value = '';
  };
  $('#btn-url').onclick = () => { $('#url-error').hidden = true; $('#url-dialog').showModal(); };
  $('#url-load').onclick = loadFromUrl;
  $('#url-cancel').onclick = () => $('#url-dialog').close();
  $('#url-input').onkeydown = (event) => {
    if (event.key === 'Enter') { event.preventDefault(); loadFromUrl(); }
  };

  // --- подсказка для первого запуска
  if (!localStorage.getItem('hint-dismissed')) {
    $('#first-hint').hidden = false;
    $('#hint-close').onclick = () => {
      $('#first-hint').hidden = true;
      try { localStorage.setItem('hint-dismissed', '1'); } catch { /* приватный режим */ }
    };
  }

  // --- горячие клавиши
  document.addEventListener('keydown', (event) => {
    const typing = event.target.matches('input, textarea, select');
    if (event.key === 'Escape') {
      if (state.focusTerm) clearTermFocus();
      return;
    }
    if (typing) return;
    if (event.key >= '1' && event.key <= String(TABS.length)) showTab(TABS[+event.key - 1].id);
    if (event.key === 'F1') { event.preventDefault(); showTab('help'); }
    if (event.key === '?') { event.preventDefault(); $('#keys-dialog').showModal(); }
    if (event.key === '/') { event.preventDefault(); $('#doc-search').focus(); }
    if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && state.collection) {
      const ids = state.collection.documents.map((d) => d.id);
      const index = ids.indexOf(state.docId);
      const next = event.key === 'ArrowDown' ? index + 1 : index - 1;
      if (next >= 0 && next < ids.length) { event.preventDefault(); selectDocument(ids[next]); }
    }
  });
}

/* Постоянные ссылки на состояние интерфейса:
     #graph:collection      — сеть всей коллекции,
     #heat:term=нейрон      — карта текста с подсветкой термина. */
async function applyHash() {
  const [tab, extra] = decodeURIComponent(location.hash.slice(1)).split(':');
  showTab(tab);
  if (tab === 'graph' && extra === 'collection' && state.graphScope !== 'collection') {
    $('#g-scope').value = 'collection';
    await $('#g-scope').onchange({ target: $('#g-scope') });
  }
  if (extra && extra.startsWith('term=')) {
    const term = extra.slice(5);
    if (term) {
      if (!state.data) await new Promise((resolve) => setTimeout(resolve, 600));
      state.focusTerm = term;
      applyTermFocus(true);
    }
  }
}

bindUi();
markChangedParams();
window.addEventListener('hashchange', applyHash);
if (location.hash) applyHash();
loadCollection().catch((error) => toast('Не удалось загрузить коллекцию: ' + error.message, 6000));
