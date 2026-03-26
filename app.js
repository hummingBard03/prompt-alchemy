const API = 'http://localhost:8000';

let currentWord = '';
let currentNear = [];
let currentFar  = [];
let history = [];
let lastPromptIdx = {};
let keywords = [];
let arithPos = [];
let arithNeg = [];

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

function renderResults(word, near, far) {
  document.getElementById('placeholder').style.display = 'none';
  document.getElementById('resultArea').style.display = 'block';
  document.getElementById('pivotWord').textContent = word;

  document.getElementById('nearChips').innerHTML = near.map(([w, score], i) =>
    `<span class="rchip rchip-near" onclick="searchWord('${w}')" title="${(score*100).toFixed(1)}%"
           style="animation-delay:${i*0.04}s">${w}</span>`
  ).join('');

  document.getElementById('farChips').innerHTML = far.map(([w], i) =>
    `<span class="rchip rchip-far" onclick="searchWord('${w}')"
           style="animation-delay:${i*0.04}s">${w}</span>`
  ).join('');

  const combo = [
    ...near.slice(0, 3).map(([w]) => [w, 'near']),
    ...far.slice(0, 3).map(([w])  => [w, 'far']),
  ];
  document.getElementById('comboChips').innerHTML = combo.map(([w, type], i) =>
    `<span class="rchip rchip-${type}" onclick="searchWord('${w}')"
           style="animation-delay:${i*0.04}s">${w}</span>`
  ).join('');
}

// ── Prompts ──
async function genPrompt(mode) {
  const p = currentWord;
  const n = shuffle(currentNear).slice(0, randomInt(3, currentNear.length));
  const f = shuffle(currentFar).slice(0, randomInt(3, currentFar.length));
  const style = document.getElementById('styleSelect').value;

  const elId = mode === 'near'  ? 'nearPrompt'
             : mode === 'far'   ? 'farPrompt'
             :                    'comboPrompt';

  const el = document.getElementById(elId);
  el.textContent = '生成中…';

  try {
    const res = await fetch(`${API}/prompt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pivot: p, near: n, far: f, mode, style, keywords }),
    });
    const data = await res.json();
    el.textContent = data.prompt;
    el.classList.remove('flash');
    void el.offsetWidth;
    el.classList.add('flash');
  } catch(e) {
    el.textContent = 'エラーが発生しました';
  }
}
function regenPrompt(mode) { if (currentWord) genPrompt(mode); }

function searchWord(word) {
  document.getElementById('wordInput').value = word;
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

// ── Analyze ──
async function analyzePrompt(elId) {
  const text = document.getElementById(elId).textContent;
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

async function doArithmetic() {
  if (arithPos.length === 0 && arithNeg.length === 0) return;
  const btn = document.getElementById('arithBtn');
  btn.disabled = true;
  btn.textContent = '...';
  document.getElementById('arithResults').innerHTML = '';

  try {
    const topn = parseInt(document.getElementById('topnSlider').value);
    const res = await fetch(`${API}/arithmetic`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ positive: arithPos, negative: arithNeg, topn }),
    });
    const data = await res.json();
    if (data.error) {
      document.getElementById('arithResults').innerHTML =
        `<span class="arith-error">${data.error}</span>`;
    } else {
      document.getElementById('arithResults').innerHTML = data.results.map(([w, score], i) =>
        `<span class="rchip rchip-arith" onclick="searchWord('${w}')" title="${(score*100).toFixed(1)}%"
               style="animation-delay:${i*0.04}s">${w}</span>`
      ).join('');
    }
  } catch(e) {
    document.getElementById('arithResults').innerHTML =
      `<span class="arith-error">エラーが発生しました</span>`;
  }

  btn.disabled = false;
  btn.textContent = '演算する';
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

// ── Init ──
document.getElementById('wordInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') search();
});
document.getElementById('keywordInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') addKeyword();
});
document.getElementById('arithPosInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') addArith('pos');
});
document.getElementById('arithNegInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') addArith('neg');
});

checkServer();
