const API = window.location.origin;

let currentWord = '';
let currentNear = [];
let currentFar  = [];
let history = [];
let keywords = [];
let arithPos = [];
let arithNeg = [];
let journeyPath = [];

// ── Server check ──
async function checkServer() {
  try {
    const r = await fetch(`${API}/similar?word=光&topn=1`);
    if (r.ok) { setStatus('online', 'サーバー接続済'); return; }
  } catch(e) {}
  setStatus('error', 'サーバー未接続');
}

function setStatus(state, text) {
  document.getElementById('statusDot').className = 'dot ' + state;
  document.getElementById('statusText').textContent = text;
}

// ── Search ──
async function search() {
  const word = document.getElementById('wordInput').value.trim();
  if (!word) return;
  const topn = parseInt(document.getElementById('topnSlider').value);

  setLoading(true);
  currentWord = word;

  try {
    const [nearRes, farRes] = await Promise.all([
      fetch(`${API}/similar?word=${encodeURIComponent(word)}&topn=${topn}`).then(r => r.json()),
      fetch(`${API}/distant?word=${encodeURIComponent(word)}&topn=${topn}`).then(r => r.json()),
    ]);

    if (nearRes.error || farRes.error) {
      showError(nearRes.error || farRes.error);
      setLoading(false);
      return;
    }

    currentNear = nearRes.results.map(r => r[0]);
    currentFar  = farRes.results.map(r => r[0]);

    renderResults(word, nearRes.results, farRes.results);
    addHistory(word);

  } catch(e) {
    showError('サーバーに接続できません');
  }
  setLoading(false);
}

function makeChip(w, type, i, score) {
  const title = score != null ? ` title="${(score*100).toFixed(1)}%"` : '';
  return `<span class="rchip rchip-${type}" onclick="searchWord('${w}')"${title} style="animation-delay:${i*0.04}s">${w}</span>`;
}

function renderResults(word, near, far) {
  document.getElementById('placeholder').style.display = 'none';
  document.getElementById('resultArea').style.display = 'block';
  document.getElementById('pivotWord').textContent = word;

  document.getElementById('nearChips').innerHTML =
    near.map(([w, score], i) => makeChip(w, 'near', i, score)).join('');
  document.getElementById('farChips').innerHTML =
    far.map(([w], i) => makeChip(w, 'far', i)).join('');

  const combo = [
    ...near.slice(0, 3).map(([w]) => [w, 'near']),
    ...far.slice(0, 3).map(([w])  => [w, 'far']),
  ];
  document.getElementById('comboChips').innerHTML =
    combo.map(([w, type], i) => makeChip(w, type, i)).join('');
}

// ── Prompts ──
async function fetchAndFlashPrompt(elId, body) {
  const el = document.getElementById(elId);
  el.textContent = '生成中…';
  try {
    const res = await fetch(`${API}/prompt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    el.textContent = data.prompt ?? 'エラーが発生しました';
    const sceneEl = document.getElementById(elId + 'Scene');
    if (sceneEl) sceneEl.textContent = data.scene_ja ?? '';
    el.classList.remove('flash');
    void el.offsetWidth;
    el.classList.add('flash');
  } catch(e) {
    el.textContent = 'エラーが発生しました';
  }
}

async function genPrompt(mode) {
  const style = document.getElementById('styleSelect').value;
  const elId = mode === 'near' ? 'nearPrompt' : mode === 'far' ? 'farPrompt' : 'comboPrompt';
  await fetchAndFlashPrompt(elId, {
    pivot: currentWord,
    near: shuffle(currentNear).slice(0, randomInt(3, currentNear.length)),
    far:  shuffle(currentFar).slice(0, randomInt(3, currentFar.length)),
    mode, style, keywords, tone: getTone(),
  });
}
function regenPrompt(mode) { if (currentWord) genPrompt(mode); }

async function randomSearch() {
  const btn = document.getElementById('randomBtn');
  btn.disabled = true;
  try {
    const res = await fetch(`${API}/random`);
    const data = await res.json();
    if (data.word) {
      document.getElementById('wordInput').value = data.word;
      search();
    }
  } catch(e) {
    console.error('random error:', e);
  }
  btn.disabled = false;
}

function searchWord(word) {
  document.getElementById('wordInput').value = word;
  const searchBtn = document.querySelector('.main-tab-btn[data-tab="searchTab"]');
  if (searchBtn && !searchBtn.classList.contains('active')) switchMainTab(searchBtn);
  search();
}

function shuffle(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function randomInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

// ── Tone ──
const TONE_AXES = ['brightness', 'quietness', 'mystery', 'warmth', 'era', 'scale', 'density', 'decay', 'mood', 'color', 'lighting', 'spatial', 'clarity'];

function getTone() {
  const tone = {};
  for (const axis of TONE_AXES) {
    const v = parseInt(document.getElementById(`tone_${axis}`).value);
    if (v !== 0) tone[axis] = v;
  }
  return tone;
}

function resetTone() {
  for (const axis of TONE_AXES) {
    document.getElementById(`tone_${axis}`).value = '0';
  }
}

// ── Analyze ──
async function analyzePrompt(elId) {
  const sceneEl = document.getElementById(elId + 'Scene');
  const text = (sceneEl && sceneEl.textContent) || document.getElementById(elId).textContent;
  if (!text || text === '生成中…') return;
  try {
    const res = await fetch(`${API}/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    if (data.words && data.words.length > 0) {
      addAnalyzedWords(data.words);
    }
  } catch(e) {
    console.error('analyze error:', e);
  }
}


// ── History ──
function addHistory(word) {
  const time = new Date().toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' });
  history = [{ word, time }, ...history.filter(h => h.word !== word)].slice(0, 20);
  renderHistory();
}

function renderHistory() {
  const el = document.getElementById('historyList');
  if (!history.length) {
    el.innerHTML = '<span style="font-size:0.65rem;color:var(--muted)">まだ検索していません</span>';
    return;
  }
  el.innerHTML = history.map(h => `
    <div class="history-item" onclick="searchWord('${h.word}')">
      <span class="history-item-word">${h.word}</span>
      <span class="history-item-time">${h.time}</span>
    </div>
  `).join('');
}

// ── UI helpers ──
function setLoading(on) {
  const btn = document.getElementById('searchBtn');
  btn.disabled = on;
  btn.textContent = on ? '...' : '展開';
}

function showError(msg) {
  document.getElementById('placeholder').style.display = 'none';
  document.getElementById('resultArea').style.display = 'block';
  document.getElementById('pivotWord').innerHTML = `<span class="error-msg">${msg}</span>`;
  document.getElementById('pivotHint').textContent = '';
  ['nearChips', 'farChips', 'comboChips'].forEach(id => {
    document.getElementById(id).innerHTML = '';
  });
}

function copyText(id) {
  const el = document.getElementById(id);
  navigator.clipboard.writeText(el.textContent).then(() => {
    el.classList.add('flash');
    setTimeout(() => el.classList.remove('flash'), 500);
  });
}

function addAnalyzedWords(words) {
  document.getElementById('analyzedSection').innerHTML = words.map((w, i) =>`
    <div class="analyze-item" onclick="searchWord('${w}')">
      <span class="analyze-item-word">${w}</span>
    </div>  
  `
  ).join('');
}

// ── Arithmetic ──
function addArith(side) {
  const arr = side === 'pos' ? arithPos : arithNeg;
  const input = document.getElementById(side === 'pos' ? 'arithPosInput' : 'arithNegInput');
  const word = input.value.trim();
  if (!word || arr.includes(word)) { input.value = ''; return; }
  arr.push(word);
  input.value = '';
  renderArith();
}

function removeArith(side, word) {
  if (side === 'pos') arithPos = arithPos.filter(w => w !== word);
  else                arithNeg = arithNeg.filter(w => w !== word);
  renderArith();
}

function renderArith() {
  document.getElementById('arithPosChips').innerHTML = arithPos.map(w =>
    `<span class="kchip">${w}<span class="kchip-remove" onclick="removeArith('pos','${w}')">✕</span></span>`
  ).join('');

  document.getElementById('arithNegChips').innerHTML = arithNeg.map(w =>
    `<span class="kchip kchip-neg">${w}<span class="kchip-remove" onclick="removeArith('neg','${w}')">✕</span></span>`
  ).join('');

  const posParts = arithPos.map((w, i) => (i === 0 ? w : `＋${w}`));
  const negParts = arithNeg.map(w => `－${w}`);
  const all = [...posParts, ...negParts];
  document.getElementById('arithFormula').textContent = all.length ? all.join(' ') + ' ＝ ？' : '';
}

async function withBtn(btnId, loadingText, doneText, fn) {
  const btn = document.getElementById(btnId);
  btn.disabled = true;
  btn.textContent = loadingText;
  await fn();
  btn.disabled = false;
  btn.textContent = doneText;
}

async function doArithmetic() {
  if (arithPos.length === 0 && arithNeg.length === 0) return;
  document.getElementById('arithResults').innerHTML = '';
  await withBtn('arithBtn', '...', '演算する', async () => {
    try {
      const topn = parseInt(document.getElementById('topnSlider').value);
      const res = await fetch(`${API}/arithmetic`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ positive: arithPos, negative: arithNeg, topn }),
      });
      const data = await res.json();
      document.getElementById('arithResults').innerHTML = data.error
        ? `<span class="arith-error">${data.error}</span>`
        : data.results.map(([w, score], i) => makeChip(w, 'arith', i, score)).join('');
    } catch(e) {
      document.getElementById('arithResults').innerHTML =
        `<span class="arith-error">エラーが発生しました</span>`;
    }
  });
}

// ── Keywords ──
function addKeyword() {
  const input = document.getElementById('keywordInput');
  const word = input.value.trim();
  if (!word || keywords.includes(word)) { input.value = ''; return; }
  keywords.push(word);
  input.value = '';
  renderKeywords();
}

function removeKeyword(word) {
  keywords = keywords.filter(k => k !== word);
  renderKeywords();
}

function renderKeywords() {
  document.getElementById('keywordsChips').innerHTML = keywords.map(w =>
    `<span class="kchip">${w}<span class="kchip-remove" onclick="removeKeyword('${w}')">✕</span></span>`
  ).join('');
}

// ── Journey ──
async function runJourney() {
  const start = document.getElementById('journeyStart').value.trim();
  const end   = document.getElementById('journeyEnd').value.trim();
  if (!start || !end) return;

  await withBtn('journeyBtn', '...', '探索する', async () => {
    try {
      const steps = parseInt(document.getElementById('stepsSlider').value);
      const res = await fetch(`${API}/journey`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ start, end, steps }),
      });
      const data = await res.json();
      if (data.error) renderJourneyError(data.error);
      else { journeyPath = data.path; renderJourneyPath(data.path); }
    } catch(e) {
      renderJourneyError('サーバーに接続できません');
    }
  });
}

function renderJourneyPath(path) {
  document.getElementById('journeyInitMsg').style.display = 'none';
  document.getElementById('journeyArea').style.display = 'block';
  document.getElementById('journeyPrompt').textContent = '';

  document.getElementById('journeyPathDisplay').innerHTML = path.map((w, i) => {
    const cls = i === 0 ? 'rchip rchip-near' : i === path.length - 1 ? 'rchip rchip-far' : 'rchip rchip-arith';
    const arrow = i < path.length - 1 ? '<span class="journey-arrow">→</span>' : '';
    return `<span class="${cls}" onclick="searchWord('${w}')" style="animation-delay:${i*0.06}s">${w}</span>${arrow}`;
  }).join('');
}

function renderJourneyError(msg) {
  document.getElementById('journeyInitMsg').style.display = 'none';
  document.getElementById('journeyArea').style.display = 'block';
  document.getElementById('journeyPathDisplay').innerHTML =
    `<span class="arith-error">${msg}</span>`;
}

async function genJourneyPrompt() {
  if (!journeyPath.length) return;
  const style = document.getElementById('styleSelect').value;
  await fetchAndFlashPrompt('journeyPrompt', {
    pivot: journeyPath[0], near: [], far: [],
    mode: 'journey', style, keywords, path: journeyPath, tone: getTone(),
  });
}

// ── Expand ──
async function runExpand() {
  const text = document.getElementById('expandInput').value.trim();
  if (!text) return;

  await withBtn('expandBtn', '...', '展開する', async () => {
    try {
      const style = document.getElementById('expandStyleSelect').value;
      const res = await fetch(`${API}/expand`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, style, keywords, tone: getTone() }),
      });
      const data = await res.json();

      document.getElementById('expandInitMsg').style.display = 'none';
      document.getElementById('expandArea').style.display = 'block';

      if (data.error) {
        document.getElementById('expandWordChips').innerHTML =
          `<span class="arith-error">${data.error}</span>`;
        document.getElementById('expandMapSection').innerHTML = '';
        document.getElementById('expandPrompt').textContent = '';
        return;
      }

      document.getElementById('expandWordChips').innerHTML =
        data.words.map((w, i) => makeChip(w, 'near', i, null)).join('');

      document.getElementById('expandMapSection').innerHTML = data.words.map(w => `
        <div style="margin-bottom:0.6rem">
          <span class="section-label label-rand" style="font-size:0.65rem">${w}</span>
          <div class="chips-row" style="margin-top:0.3rem">
            ${data.word_map[w].map((n, i) => makeChip(n, 'arith', i, null)).join('')}
          </div>
        </div>
      `).join('');

      const el = document.getElementById('expandPrompt');
      el.textContent = data.prompt;
      const sceneEl = document.getElementById('expandPromptScene');
      if (sceneEl) sceneEl.textContent = data.scene_ja ?? '';
      el.classList.remove('flash');
      void el.offsetWidth;
      el.classList.add('flash');
    } catch(e) {
      document.getElementById('expandPrompt').textContent = 'エラーが発生しました';
    }
  });
}

// ── Tabs ──
function switchMainTab(btn) {
  document.querySelectorAll('.main-tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.main-tab-pane').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById(btn.dataset.tab).classList.add('active');
}

function switchTab(btn, groupId) {
  const group = document.getElementById(groupId);
  const tabId = btn.dataset.tab;
  group.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  group.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById(tabId).classList.add('active');
}

// ── Init ──
[
  ['wordInput',     () => search()],
  ['keywordInput',  () => addKeyword()],
  ['arithPosInput', () => addArith('pos')],
  ['arithNegInput', () => addArith('neg')],
  ['journeyStart',  () => document.getElementById('journeyEnd').focus()],
  ['journeyEnd',    () => runJourney()],
].forEach(([id, fn]) => {
  document.getElementById(id).addEventListener('keydown', e => { if (e.key === 'Enter') fn(); });
});

checkServer();
