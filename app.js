// API のベース URL（同一オリジン）
const API = window.location.origin;

// ── グローバル状態 ──
let currentWord = '';    // 現在の検索ピボット単語
let currentNear = [];    // ピボットに近い単語リスト
let currentFar  = [];    // ピボットと遠い単語リスト
let history = [];        // 検索履歴（最大20件）
let keywords = [];       // プロンプトに必ず含めるキーワードリスト
let arithPos = [];       // 単語演算の加算側リスト
let arithNeg = [];       // 単語演算の減算側リスト
let journeyPath = [];    // 最後に生成した旅の経路（プロンプト生成に使用）

// ── Server check ──

/**
 * サーバーとの疎通確認を行い、ステータスドットを更新する。
 * /similar?word=光 を試験リクエストとして使用する。
 * @returns {Promise<void>}
 */
async function checkServer() {
  try {
    const r = await fetch(`${API}/similar?word=光&topn=1`);
    if (r.ok) { setStatus('online', 'サーバー接続済'); return; }
  } catch(e) {}
  setStatus('error', 'サーバー未接続');
}

/**
 * ステータスドットのクラスとテキストをまとめて更新する。
 * @param {'online'|'error'} state - ドットに付与する CSS クラス名。
 * @param {string} text - ステータスバーに表示するテキスト。
 */
function setStatus(state, text) {
  document.getElementById('statusDot').className = 'dot ' + state;
  document.getElementById('statusText').textContent = text;
}

// ── Search ──

/**
 * 入力フォームの単語で /similar・/distant を並列呼び出しし、結果を描画する。
 * 成功時は currentNear / currentFar を更新して renderResults を呼び出す。
 * @returns {Promise<void>}
 */
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

/**
 * 単語チップの HTML 文字列を生成する。
 * クリックで searchWord を呼び出し、スコアがあれば tooltip として表示する。
 * @param {string} w - 表示する単語。
 * @param {string} type - チップの種別（"near" | "far" | "arith" など）。CSS クラス名に使用。
 * @param {number} i - アニメーション遅延計算用のインデックス。
 * @param {number|null} score - コサイン類似度（0〜1）。null の場合は tooltip を付与しない。
 * @returns {string} チップの HTML 文字列。
 */
function makeChip(w, type, i, score) {
  const title = score != null ? ` title="${(score*100).toFixed(1)}%"` : '';
  return `<span class="rchip rchip-${type}" onclick="searchWord('${w}')"${title} style="animation-delay:${i*0.04}s">${w}</span>`;
}

/**
 * 検索結果エリアを表示し、near / far / combo の各チップ列を描画する。
 * combo は near・far それぞれ上位3語を混合して表示する。
 * @param {string} word - ピボット単語。
 * @param {Array<[string, number]>} near - 類似語と類似度のペア配列。
 * @param {Array<[string, number]>} far - 対極語と類似度のペア配列。
 */
function renderResults(word, near, far) {
  document.getElementById('placeholder').style.display = 'none';
  document.getElementById('resultArea').style.display = 'block';
  document.getElementById('pivotWord').textContent = word;

  document.getElementById('nearChips').innerHTML =
    near.map(([w, score], i) => makeChip(w, 'near', i, score)).join('');
  document.getElementById('farChips').innerHTML =
    far.map(([w], i) => makeChip(w, 'far', i)).join('');

  // combo は near/far それぞれ上位3語を混合して表示する
  const combo = [
    ...near.slice(0, 3).map(([w]) => [w, 'near']),
    ...far.slice(0, 3).map(([w])  => [w, 'far']),
  ];
  document.getElementById('comboChips').innerHTML =
    combo.map(([w, type], i) => makeChip(w, type, i)).join('');
}

// ── Prompts ──

/**
 * /prompt API を呼び出して結果を指定要素に表示し、フラッシュアニメーションを付与する。
 * `${elId}Scene` 要素が存在すれば日本語情景説明も更新する。
 * @param {string} elId - プロンプトを表示する要素の ID。
 * @param {Object} body - /prompt API に POST するリクエストボディ。
 * @returns {Promise<void>}
 */
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
    // 対応する Scene 要素があれば日本語情景説明も更新する
    const sceneEl = document.getElementById(elId + 'Scene');
    if (sceneEl) sceneEl.textContent = data.scene_ja ?? '';
    // 再描画をトリガするためいったんクラスを外してから付け直す
    el.classList.remove('flash');
    void el.offsetWidth;
    el.classList.add('flash');
  } catch(e) {
    el.textContent = 'エラーが発生しました';
  }
}

/**
 * 指定モード（near / far / combo）でプロンプトを生成する。
 * near/far の単語はシャッフル後にランダム件数サブサンプリングし、毎回異なる結果を得る。
 * @param {'near'|'far'|'combo'} mode - プロンプト生成モード。
 * @returns {Promise<void>}
 */
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

/**
 * 検索済みの場合のみプロンプトを再生成する。
 * @param {'near'|'far'|'combo'} mode - プロンプト生成モード。
 */
function regenPrompt(mode) { if (currentWord) genPrompt(mode); }

/**
 * /random API からランダム単語を取得し、そのまま search を実行する。
 * @returns {Promise<void>}
 */
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

/**
 * 指定単語を入力フィールドにセットし、検索タブへ切り替えてから search を実行する。
 * チップクリック時のハンドラとして使用する。
 * @param {string} word - 検索する単語。
 */
function searchWord(word) {
  document.getElementById('wordInput').value = word;
  const searchBtn = document.querySelector('.main-tab-btn[data-tab="searchTab"]');
  if (searchBtn && !searchBtn.classList.contains('active')) switchMainTab(searchBtn);
  search();
}

/**
 * Fisher–Yates アルゴリズムで配列をシャッフルしたコピーを返す。
 * 元の配列は変更しない。
 * @template T
 * @param {T[]} arr - シャッフル対象の配列。
 * @returns {T[]} シャッフルされた新しい配列。
 */
function shuffle(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

/**
 * min〜max の整数をランダムに返す（両端含む）。
 * @param {number} min - 最小値（含む）。
 * @param {number} max - 最大値（含む）。
 * @returns {number} ランダムな整数。
 */
function randomInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

// ── Tone ──

// TONE_MAP と対応するトーン軸の識別子リスト
const TONE_AXES = ['brightness', 'quietness', 'mystery', 'warmth', 'era', 'scale', 'density', 'decay', 'mood', 'color', 'lighting', 'spatial', 'clarity'];

/**
 * 各軸のスライダー値を読み取り、0 以外の軸のみ含む tone オブジェクトを返す。
 * @returns {{[axis: string]: number}} 軸名 → 強度値（-3〜3）の辞書。値が 0 の軸は含まない。
 */
function getTone() {
  const tone = {};
  for (const axis of TONE_AXES) {
    const v = parseInt(document.getElementById(`tone_${axis}`).value);
    if (v !== 0) tone[axis] = v;
  }
  return tone;
}

/**
 * 全トーン軸のスライダーを 0（中立）にリセットする。
 */
function resetTone() {
  for (const axis of TONE_AXES) {
    document.getElementById(`tone_${axis}`).value = '0';
  }
}

// ── Analyze ──

/**
 * 表示中のプロンプトまたは情景説明を /analyze に送り、抽出された単語を分析セクションに表示する。
 * `${elId}Scene` 要素があれば情景説明を優先し、なければプロンプト本文を解析対象にする。
 * @param {string} elId - プロンプト要素の ID。
 * @returns {Promise<void>}
 */
async function analyzePrompt(elId) {
  const sceneEl = document.getElementById(elId + 'Scene');
  // 情景説明があればそちらを優先し、なければプロンプト本文を解析対象にする
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

/**
 * 検索履歴に単語を追加する。
 * 同じ単語が既にある場合は先頭に移動し、最大 20 件を超えた分は末尾から削除する。
 * @param {string} word - 追加する単語。
 */
function addHistory(word) {
  const time = new Date().toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' });
  history = [{ word, time }, ...history.filter(h => h.word !== word)].slice(0, 20);
  renderHistory();
}

/**
 * 検索履歴リストを再描画する。
 * 履歴が空の場合はプレースホルダーテキストを表示する。
 */
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

/**
 * 検索ボタンの disabled 状態とラベルを切り替える。
 * @param {boolean} on - true でローディング状態に、false で通常状態に戻す。
 */
function setLoading(on) {
  const btn = document.getElementById('searchBtn');
  btn.disabled = on;
  btn.textContent = on ? '...' : '展開';
}

/**
 * エラーメッセージをピボット欄に表示し、near / far / combo のチップ列をクリアする。
 * @param {string} msg - 表示するエラーメッセージ。
 */
function showError(msg) {
  document.getElementById('placeholder').style.display = 'none';
  document.getElementById('resultArea').style.display = 'block';
  document.getElementById('pivotWord').innerHTML = `<span class="error-msg">${msg}</span>`;
  document.getElementById('pivotHint').textContent = '';
  ['nearChips', 'farChips', 'comboChips'].forEach(id => {
    document.getElementById(id).innerHTML = '';
  });
}

/**
 * 指定要素のテキストをクリップボードにコピーし、フラッシュアニメーションで完了を通知する。
 * @param {string} id - コピー対象要素の ID。
 */
function copyText(id) {
  const el = document.getElementById(id);
  navigator.clipboard.writeText(el.textContent).then(() => {
    el.classList.add('flash');
    setTimeout(() => el.classList.remove('flash'), 500);
  });
}

/**
 * 分析結果の単語を分析セクションに描画する。
 * 各アイテムをクリックすると searchWord が呼び出される。
 * @param {string[]} words - 表示する単語の配列。
 */
function addAnalyzedWords(words) {
  document.getElementById('analyzedSection').innerHTML = words.map(w =>`
    <div class="analyze-item" onclick="searchWord('${w}')">
      <span class="analyze-item-word">${w}</span>
    </div>
  `
  ).join('');
}

// ── Evaluate ──

/**
 * 表示中のプロンプトを /evaluate API に送り、スコアと改善提案を描画する。
 * 総合スコア・5次元バー・改善提案リストを evalEl に挿入する。
 * @param {string} promptId - 評価対象のプロンプト要素 ID。
 *   対応する Scene 要素（`${promptId}Scene`）と評価表示先（`${promptId}Eval`）も使用する。
 * @returns {Promise<void>}
 */
async function evaluatePrompt(promptId) {
  const promptEl = document.getElementById(promptId);
  const sceneEl = document.getElementById(promptId + 'Scene');
  const evalEl = document.getElementById(promptId + 'Eval');
  if (!promptEl || !evalEl) return;

  const promptText = promptEl.textContent.trim();
  const sceneText = sceneEl ? sceneEl.textContent.trim() : '';
  if (!promptText || promptText === '生成中…' || promptText.length < 10) return;

  evalEl.style.display = 'block';
  evalEl.innerHTML = '<span class="eval-loading">評価中…</span>';

  try {
    const res = await fetch(`${API}/evaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: promptText, scene_ja: sceneText }),
    });
    const data = await res.json();

    if (data.error) {
      evalEl.innerHTML = `<span class="arith-error">${data.error}</span>`;
      return;
    }

    // 5次元スコアの表示定義（キー・ラベル・バーカラーの対応）
    const dims = data.dimensions || {};
    const dimDefs = [
      { key: 'subject',     label: '被写体',  color: '--green'  },
      { key: 'composition', label: '構図',    color: '--blue'   },
      { key: 'lighting',    label: '光',      color: '--yellow' },
      { key: 'mood',        label: '雰囲気',  color: '--pink'   },
      { key: 'detail',      label: '詳細度',  color: '--gold'   },
    ];

    // 各次元をプログレスバー付きで HTML に変換する（スコア 0-10 → 幅 0-100%）
    const dimsHtml = dimDefs.map(({ key, label, color }) => {
      const val = dims[key] ?? 0;
      return `
        <div class="eval-dim">
          <span class="eval-dim-label">${label}</span>
          <div class="eval-bar-wrap">
            <div class="eval-bar" style="width:${val * 10}%;background:var(${color})"></div>
          </div>
          <span class="eval-dim-score">${val}</span>
        </div>`;
    }).join('');

    const suggestions = data.suggestions || [];
    const suggestionsHtml = suggestions.length
      ? `<div class="eval-suggestions-label">// 改善提案</div>
         <ul class="eval-suggestions">${suggestions.map(s => `<li class="eval-suggestion">・${s}</li>`).join('')}</ul>`
      : '';

    // 総合スコアに応じてカラーを変える（80以上: 緑、60以上: 金、それ未満: ピンク）
    const score = data.score ?? 0;
    const scoreColor = score >= 80 ? 'var(--green)' : score >= 60 ? 'var(--gold)' : 'var(--pink)';

    evalEl.innerHTML = `
      <div class="eval-header">
        <span class="eval-label">// 品質評価</span>
        <span class="eval-score" style="color:${scoreColor}">${score}<span class="eval-score-max">/100</span></span>
      </div>
      <div class="eval-dims">${dimsHtml}</div>
      ${suggestionsHtml}`;
  } catch(e) {
    evalEl.innerHTML = '<span class="arith-error">評価に失敗しました</span>';
  }
}

// ── Arithmetic ──

/**
 * 単語演算の加算または減算リストに単語を追加する。重複は無視する。
 * @param {'pos'|'neg'} side - 追加先リスト（'pos': 加算、'neg': 減算）。
 */
function addArith(side) {
  const arr = side === 'pos' ? arithPos : arithNeg;
  const input = document.getElementById(side === 'pos' ? 'arithPosInput' : 'arithNegInput');
  const word = input.value.trim();
  if (!word || arr.includes(word)) { input.value = ''; return; }
  arr.push(word);
  input.value = '';
  renderArith();
}

/**
 * 単語演算リストから指定単語を削除する。
 * @param {'pos'|'neg'} side - 削除対象のリスト（'pos': 加算、'neg': 減算）。
 * @param {string} word - 削除する単語。
 */
function removeArith(side, word) {
  if (side === 'pos') arithPos = arithPos.filter(w => w !== word);
  else                arithNeg = arithNeg.filter(w => w !== word);
  renderArith();
}

/**
 * 演算チップと数式プレビュー（例: "王 ＋ 女 － 男 ＝ ？"）を再描画する。
 */
function renderArith() {
  document.getElementById('arithPosChips').innerHTML = arithPos.map(w =>
    `<span class="kchip">${w}<span class="kchip-remove" onclick="removeArith('pos','${w}')">✕</span></span>`
  ).join('');

  document.getElementById('arithNegChips').innerHTML = arithNeg.map(w =>
    `<span class="kchip kchip-neg">${w}<span class="kchip-remove" onclick="removeArith('neg','${w}')">✕</span></span>`
  ).join('');

  // 数式プレビュー: pos は「A ＋ B」、neg は「－ C」の形式で表示する
  const posParts = arithPos.map((w, i) => (i === 0 ? w : `＋${w}`));
  const negParts = arithNeg.map(w => `－${w}`);
  const all = [...posParts, ...negParts];
  document.getElementById('arithFormula').textContent = all.length ? all.join(' ') + ' ＝ ？' : '';
}

/**
 * ボタンをローディング状態にして非同期処理を実行し、完了後に通常状態へ戻すヘルパー。
 * @param {string} btnId - 操作対象のボタン要素 ID。
 * @param {string} loadingText - 処理中に表示するボタンラベル。
 * @param {string} doneText - 処理完了後に表示するボタンラベル。
 * @param {() => Promise<void>} fn - 実行する非同期処理。
 * @returns {Promise<void>}
 */
async function withBtn(btnId, loadingText, doneText, fn) {
  const btn = document.getElementById(btnId);
  btn.disabled = true;
  btn.textContent = loadingText;
  await fn();
  btn.disabled = false;
  btn.textContent = doneText;
}

/**
 * /arithmetic API を呼び出し、単語ベクトル演算の結果をチップとして表示する。
 * arithPos / arithNeg が両方空の場合は何もしない。
 * @returns {Promise<void>}
 */
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

/**
 * 必須キーワードリストに単語を追加する。重複は無視する。
 */
function addKeyword() {
  const input = document.getElementById('keywordInput');
  const word = input.value.trim();
  if (!word || keywords.includes(word)) { input.value = ''; return; }
  keywords.push(word);
  input.value = '';
  renderKeywords();
}

/**
 * 必須キーワードリストから指定単語を削除する。
 * @param {string} word - 削除するキーワード。
 */
function removeKeyword(word) {
  keywords = keywords.filter(k => k !== word);
  renderKeywords();
}

/**
 * キーワードチップを再描画する。
 */
function renderKeywords() {
  document.getElementById('keywordsChips').innerHTML = keywords.map(w =>
    `<span class="kchip">${w}<span class="kchip-remove" onclick="removeKeyword('${w}')">✕</span></span>`
  ).join('');
}

// ── Journey ──

/**
 * /journey API を呼び出して start〜end 間の経路を探索し、結果を描画する。
 * 入力フィールドから start・end・steps を読み取る。
 * @returns {Promise<void>}
 */
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

/**
 * 旅の経路を単語チップ + 矢印で描画する。
 * 先頭は near 色、末尾は far 色、中間語は arith 色で表示する。
 * @param {string[]} path - 経路単語の配列（先頭が start、末尾が end）。
 */
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

/**
 * 旅の経路探索でエラーが発生した場合のメッセージを journeyPathDisplay に表示する。
 * @param {string} msg - 表示するエラーメッセージ。
 */
function renderJourneyError(msg) {
  document.getElementById('journeyInitMsg').style.display = 'none';
  document.getElementById('journeyArea').style.display = 'block';
  document.getElementById('journeyPathDisplay').innerHTML =
    `<span class="arith-error">${msg}</span>`;
}

/**
 * journeyPath を使って journey モードでプロンプトを生成し、journeyPrompt 要素に表示する。
 * journeyPath が空の場合は何もしない。
 * @returns {Promise<void>}
 */
async function genJourneyPrompt() {
  if (!journeyPath.length) return;
  const style = document.getElementById('styleSelect').value;
  await fetchAndFlashPrompt('journeyPrompt', {
    pivot: journeyPath[0], near: [], far: [],
    mode: 'journey', style, keywords, path: journeyPath, tone: getTone(),
  });
}

// ── Expand ──

/**
 * 入力テキストを /expand API に送り、抽出語・類似語クラスタ・プロンプトを表示する。
 * @returns {Promise<void>}
 */
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

      // 抽出された主要語をチップとして表示する
      document.getElementById('expandWordChips').innerHTML =
        data.words.map((w, i) => makeChip(w, 'near', i, null)).join('');

      // 各主要語の類似語クラスタをセクションごとに表示する
      document.getElementById('expandMapSection').innerHTML = data.words.map(w => `
        <div style="margin-bottom:0.6rem">
          <span class="section-label label-rand" style="font-size:0.65rem">${w}</span>
          <div class="chips-row" style="margin-top:0.3rem">
            ${data.word_map[w].map((n, i) => makeChip(n, 'arith', i, null)).join('')}
          </div>
        </div>
      `).join('');

      // 生成プロンプトを表示してフラッシュアニメーションを起動する
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

// ── Cluster ──

let clusterWords = [];  // 共通探索の入力単語リスト

/**
 * 共通探索リストに単語を追加する。重複は無視する。
 */
function addClusterWord() {
  const input = document.getElementById('clusterInput');
  const word = input.value.trim();
  if (!word || clusterWords.includes(word)) { input.value = ''; return; }
  clusterWords.push(word);
  input.value = '';
  renderClusterChips();
}

/**
 * 共通探索リストから単語を削除する。
 * @param {string} word - 削除する単語。
 */
function removeClusterWord(word) {
  clusterWords = clusterWords.filter(w => w !== word);
  renderClusterChips();
}

/**
 * 共通探索の入力チップを再描画する。
 */
function renderClusterChips() {
  document.getElementById('clusterChips').innerHTML = clusterWords.map(w =>
    `<span class="kchip">${w}<span class="kchip-remove" onclick="removeClusterWord('${escAttr(w)}')">✕</span></span>`
  ).join('');
}

/**
 * /cluster API を呼び出し、共通近傍語をチップとして表示する。
 * @returns {Promise<void>}
 */
async function doCluster() {
  if (clusterWords.length < 2) return;
  document.getElementById('clusterResults').innerHTML = '';
  await withBtn('clusterBtn', '...', '探索する', async () => {
    try {
      const topn = parseInt(document.getElementById('topnSlider').value);
      const res = await fetch(`${API}/cluster`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ words: clusterWords, topn }),
      });
      const data = await res.json();
      const resultsEl = document.getElementById('clusterResults');
      document.getElementById('clusterInitMsg').style.display = 'none';
      resultsEl.innerHTML = data.error
        ? `<span class="arith-error">${esc(data.error)}</span>`
        : `<div class="chips-row" style="padding:0.5rem 0">${
            data.results.map(([w, score], i) => makeChip(w, 'arith', i, score)).join('')
          }</div>`;
    } catch(e) {
      document.getElementById('clusterResults').innerHTML =
        '<span class="arith-error">エラーが発生しました</span>';
    }
  });
}

// ── Log History ──

// 履歴タブを一度でも読み込んだかのフラグ
let logLoaded = false;

/**
 * HTML 特殊文字をエスケープして XSS を防ぐ。
 * @param {string} s - エスケープ対象の文字列。
 * @returns {string} エスケープ済み文字列。
 */
function esc(s) {
  const d = document.createElement('div');
  d.textContent = String(s ?? '');
  return d.innerHTML;
}

/**
 * onclick 属性用にシングルクォートをエスケープする。
 * @param {string} s - エスケープ対象の文字列。
 * @returns {string} エスケープ済み文字列。
 */
function escAttr(s) {
  return String(s ?? '').replace(/'/g, "\\'");
}

/**
 * /history API から生成履歴を取得し、logEntries に描画する。
 * logSearchInput の値を検索クエリとして使用する。
 * @returns {Promise<void>}
 */
async function loadLogHistory() {
  const q = document.getElementById('logSearchInput').value.trim();
  const initMsg = document.getElementById('logInitMsg');
  const entriesEl = document.getElementById('logEntries');

  initMsg.style.display = 'none';
  entriesEl.style.display = 'flex';
  entriesEl.innerHTML = '<span class="eval-loading" style="padding:2rem 0;text-align:center">読み込み中…</span>';

  try {
    const url = `${API}/history?limit=50${q ? '&q=' + encodeURIComponent(q) : ''}`;
    const res = await fetch(url);
    const data = await res.json();

    if (!data.entries || data.entries.length === 0) {
      entriesEl.innerHTML = '<span class="tool-init-msg">履歴がありません</span>';
      return;
    }

    entriesEl.innerHTML = data.entries.map(renderLogEntry).join('');
  } catch(e) {
    entriesEl.innerHTML = '<span class="arith-error">読み込みに失敗しました</span>';
  }

  logLoaded = true;
}

/**
 * ログエントリを HTML カードとして描画する。
 * プロンプト要素には一意の ID を付与し、既存の evaluatePrompt / copyText と連携する。
 * @param {Object} entry - ログエントリ（timestamp / endpoint / params / scene_ja / prompt）。
 * @returns {string} カードの HTML 文字列。
 */
function renderLogEntry(entry) {
  const ts = new Date(entry.timestamp);
  const dateStr = ts.toLocaleDateString('ja-JP', { month: 'numeric', day: 'numeric', timeZone: 'Asia/Tokyo' });
  const timeStr = ts.toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Tokyo' });

  const sourceLabel = { '/prompt': '検索', '/expand': '文章展開' }[entry.endpoint] ?? entry.endpoint;

  const scene = entry.scene_ja ?? '';
  const prompt = entry.prompt ?? '';
  // 一意な要素 ID を生成（タイムスタンプ + ランダム接尾辞）
  const pid = 'log-' + ts.getTime() + '-' + Math.random().toString(36).slice(2, 6);

  const pivotWord = entry.params?.pivot ?? '';
  const reuseBtn = pivotWord
    ? `<button class="btn-ghost btn-sm" onclick="searchWord('${escAttr(pivotWord)}')">「${esc(pivotWord)}」で再検索</button>`
    : '';

  return `
    <div class="log-entry-card">
      <div class="log-entry-header">
        <span class="log-entry-date">${esc(dateStr)} ${esc(timeStr)}</span>
        <span class="log-entry-source">${esc(sourceLabel)}</span>
        ${pivotWord ? `<span class="log-entry-pivot">${esc(pivotWord)}</span>` : ''}
      </div>
      <div class="log-entry-scene">${esc(scene)}</div>
      <div id="${pid}Scene" style="display:none">${esc(scene)}</div>
      <div class="log-entry-prompt" id="${pid}">${esc(prompt)}</div>
      <div class="prompt-actions">
        <button class="btn-ghost btn-sm" onclick="copyText('${pid}')">コピー</button>
        <button class="btn-ghost btn-sm" onclick="evaluatePrompt('${pid}')">品質評価</button>
        ${reuseBtn}
      </div>
      <div class="eval-card" id="${pid}Eval" style="display:none"></div>
    </div>`;
}

// ── Tabs ──

/**
 * メインタブ（Search / Journey / Expand / Arithmetic）を切り替える。
 * @param {HTMLElement} btn - クリックされたタブボタン要素。data-tab 属性でペインを特定する。
 */
function switchMainTab(btn) {
  document.querySelectorAll('.main-tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.main-tab-pane').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById(btn.dataset.tab).classList.add('active');
  // 生成履歴タブを初めて開いたとき自動読み込みする
  if (btn.dataset.tab === 'logTab' && !logLoaded) loadLogHistory();
}

/**
 * 指定グループ内のサブタブを切り替える。
 * @param {HTMLElement} btn - クリックされたタブボタン要素。data-tab 属性でペインを特定する。
 * @param {string} groupId - タブグループのコンテナ要素 ID。
 */
function switchTab(btn, groupId) {
  const group = document.getElementById(groupId);
  const tabId = btn.dataset.tab;
  group.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  group.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById(tabId).classList.add('active');
}

// ── Init ──

// 各入力フィールドに Enter キーのショートカットを一括登録する
[
  ['wordInput',     () => search()],
  ['keywordInput',  () => addKeyword()],
  ['arithPosInput', () => addArith('pos')],
  ['arithNegInput', () => addArith('neg')],
  ['journeyStart',  () => document.getElementById('journeyEnd').focus()],
  ['journeyEnd',    () => runJourney()],
  ['clusterInput',   () => addClusterWord()],
  ['logSearchInput', () => loadLogHistory()],
].forEach(([id, fn]) => {
  document.getElementById(id).addEventListener('keydown', e => { if (e.key === 'Enter') fn(); });
});

checkServer();
