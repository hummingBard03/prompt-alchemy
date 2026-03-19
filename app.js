const API = 'http://localhost:8000';

let currentWord = '';
let currentNear = [];
let currentFar  = [];
let history = [];
let lastPromptIdx = {};

// ── Templates ──
const T_NEAR = [
  (p, n) => `${n[0]} の気配を帯びた ${p}、${n[1]} に滲む光`,
  (p, n) => `${p} と ${n[0]} が溶け合う情景、${n[1]} の息遣い`,
  (p, n) => `${n[0]} に包まれた ${p}、${n[1]} な質感の中で`,
  (p, n) => `${p} の内側にある ${n[0]}、${n[1]} が漂う空気`,
];
const T_FAR = [
  (p, f) => `${p} の対極に ${f[0]} が佇む、${f[1]} との断絶`,
  (p, f) => `${f[0]} の中に ${p} が宿る矛盾、${f[1]} の予感`,
  (p, f) => `${p} から ${f[0]} へと反転する瞬間、${f[1]} の余韻`,
  (p, f) => `${f[0]} に侵食される ${p}、${f[1]} が広がる地平`,
];
const T_COMBO = [
  (p, n, f) => `${n[0]} と ${f[0]} が交差する ${p}、${n[1]} の質感`,
  (p, n, f) => `${f[0]} の中に ${n[0]} が宿る、${p} に漂う余白`,
  (p, n, f) => `${p} — ${n[0]} の息遣い × ${f[0]} の静寂`,
  (p, n, f) => `${n[0]} に滲む ${p}、${f[0]} へと反転する光`,
];

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

  genPrompt('near');
  genPrompt('far');
  genPrompt('combo');
}

// ── Prompts ──
function genPrompt(mode) {
  const p = currentWord;
  const n = currentNear.length >= 2 ? currentNear : ['静寂', '余白'];
  const f = currentFar.length  >= 2 ? currentFar  : ['虚空', '彼方'];

  const templates = mode === 'near' ? T_NEAR : mode === 'far' ? T_FAR : T_COMBO;
  const elId      = mode === 'near' ? 'nearPrompt' : mode === 'far' ? 'farPrompt' : 'comboPrompt';

  let idx;
  do { idx = Math.floor(Math.random() * templates.length); }
  while (idx === lastPromptIdx[mode] && templates.length > 1);
  lastPromptIdx[mode] = idx;

  const text = mode === 'combo' ? templates[idx](p, n, f)
             : mode === 'near'  ? templates[idx](p, n)
             :                    templates[idx](p, f);

  const el = document.getElementById(elId);
  el.textContent = text;
  el.classList.remove('flash');
  void el.offsetWidth;
  el.classList.add('flash');
}

function regenPrompt(mode) { if (currentWord) genPrompt(mode); }

function searchWord(word) {
  document.getElementById('wordInput').value = word;
  search();
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

// ── Init ──
document.getElementById('wordInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') search();
});

checkServer();
