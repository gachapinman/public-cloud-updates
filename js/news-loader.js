/**
 * news-loader.js
 * data/news.json を取得して各クラウドのニュースグリッドをアイコン付きで動的レンダリング。
 * カテゴリフィルターバー付き（クリックでカテゴリ絞り込み）。
 */

// カテゴリ設定（アイコン・ラベル・カラー）
const TAG_CONFIG = {
  'ai-tag':        { icon: '🤖', label: 'AI / ML' },
  'security-tag':  { icon: '🔒', label: 'セキュリティ' },
  'container-tag': { icon: '📦', label: 'コンテナ' },
  'database-tag':  { icon: '🗄️', label: 'データベース' },
  'storage-tag':   { icon: '💾', label: 'ストレージ' },
  'network-tag':   { icon: '🌐', label: 'ネットワーク' },
  'compute-tag':   { icon: '⚡', label: 'コンピューティング' },
};

// 各クラウドのメタ情報（Wikimedia Commons 公式SVGロゴ）
const CLOUD_META = {
  azure: { name: 'Azure', colorClass: 'azure', icon: 'https://upload.wikimedia.org/wikipedia/commons/a/a8/Microsoft_Azure_Logo.svg' },
  aws:   { name: 'AWS',   colorClass: 'aws',   icon: 'https://upload.wikimedia.org/wikipedia/commons/9/93/Amazon_Web_Services_Logo.svg' },
  gcp:   { name: 'GCP',   colorClass: 'gcp',   icon: 'https://upload.wikimedia.org/wikipedia/commons/5/51/Google_Cloud_logo.svg' },
  oci:   { name: 'OCI',   colorClass: 'oci',   icon: 'https://upload.wikimedia.org/wikipedia/commons/5/50/Oracle_logo.svg' },
};

// 各クラウドの全アイテムをキャッシュ
 const cloudItems = {};
const DEFAULT_COUNT = 6;
const COUNT_OPTIONS = [6, 12, 20];

/** HTML エスケープ */
function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** ニュースカード HTML を生成（featured 廃止 → 日付順で最新が先頭） */
function renderCard(item) {
  const cfg = TAG_CONFIG[item.category] || { icon: '☁️', label: item.cat_label || 'その他' };
  const catClass = item.category || 'compute-tag';

  return `
    <article class="news-card fade-in" data-category="${escHtml(item.category)}">
      <div class="news-category ${catClass}">
        <span class="cat-icon">${cfg.icon}</span>${cfg.label}
      </div>
      <h3 class="news-title">
        <a href="${escHtml(item.link)}" target="_blank" rel="noopener noreferrer">${escHtml(item.title)}</a>
      </h3>
      <p class="news-summary">${escHtml(item.summary)}</p>
      <div class="news-meta">
        <time datetime="${escHtml(item.date_iso)}">${escHtml(item.date)}</time>
        <a href="${escHtml(item.link)}" target="_blank" rel="noopener noreferrer" class="news-read-more">元記事を見る →</a>
      </div>
    </article>`;
}

/**
 * フィルターバーを構築してイベントを登録する。
 * items に含まれるカテゴリを自動検出してボタンを生成。
 */
function buildFilterBar(filterId, items, gridId) {
  const bar = document.getElementById(filterId);
  if (!bar) return;

  // このクラウドに存在するカテゴリを出現順で重複なし収集
  const seen = new Set();
  const cats = [];
  for (const item of items) {
    if (item.category && !seen.has(item.category)) {
      seen.add(item.category);
      cats.push(item.category);
    }
  }

  // 「すべて」ボタン + カテゴリボタン生成
  let html = `<button class="filter-btn active" data-cat="all" data-grid="${gridId}">すべて</button>`;
  for (const cat of cats) {
    const cfg = TAG_CONFIG[cat] || { icon: '☁️', label: cat };
    html += `<button class="filter-btn ${cat}" data-cat="${cat}" data-grid="${gridId}">
      <span class="filter-icon">${cfg.icon}</span>${cfg.label}
    </button>`;
  }
  bar.innerHTML = html;

  // クリックイベント（委譲）
  bar.addEventListener('click', e => {
    const btn = e.target.closest('.filter-btn');
    if (!btn) return;

    // アクティブ切り替え
    bar.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    const cat = btn.dataset.cat;
    const grid = document.getElementById(btn.dataset.grid);
    if (!grid) return;

    grid.querySelectorAll('.news-card').forEach(card => {
      const match = cat === 'all' || card.dataset.category === cat;
      card.style.display = match ? '' : 'none';
    });
  });
}

/** 最新情報ハイライトセクションを描画する（全クラウド横断 1枠6件リスト）*/
function renderLatestSummary(data) {
  const grid = document.getElementById('latest-updates-grid');
  if (!grid) return;

  // 全クラウドのアイテムをフラットにまとめ、日付降順で上位6件を取得
  const allItems = [];
  Object.entries(CLOUD_META).forEach(([cloudId, meta]) => {
    const rawItems = (data.clouds && data.clouds[cloudId]) ? data.clouds[cloudId] : [];
    rawItems.forEach(item => allItems.push({ ...item, _cloudId: cloudId, _meta: meta }));
  });

  const top6 = allItems
    .sort((a, b) => (b.date_iso || '').localeCompare(a.date_iso || ''))
    .slice(0, 6);

  if (top6.length === 0) {
    grid.innerHTML = '<p class="grid-loading">データがありません</p>';
    return;
  }

  const rows = top6.map(item => {
    const meta = item._meta;
    const cfg = TAG_CONFIG[item.category] || { icon: '☁️', label: item.cat_label || '' };
    return `
      <div class="latest-row latest-row-${meta.colorClass}">
        <div class="latest-row-cloud">
          <img src="${meta.icon}" alt="${meta.name}" class="latest-row-icon" />
          <span class="latest-row-name">${meta.name}</span>
        </div>
        <span class="latest-row-cat">${cfg.icon} ${cfg.label}</span>
        <a href="${escHtml(item.link)}" target="_blank" rel="noopener noreferrer" class="latest-row-title">${escHtml(item.title)}</a>
        <time class="latest-row-date">${escHtml(item.date)}</time>
      </div>`;
  });

  grid.innerHTML = `<div class="latest-panel">${rows.join('')}</div>`;
}

/** 件数セレクターを構築する */
function buildCountSelector(cloudId, totalAvailable) {
  const el = document.getElementById(`${cloudId}-count`);
  if (!el) return;
  if (totalAvailable <= DEFAULT_COUNT) {
    el.style.display = 'none';
    return;
  }
  const buttons = COUNT_OPTIONS.map(n => {
    const active = n === DEFAULT_COUNT ? ' active' : '';
    return `<button class="count-btn${active}" data-count="${n}" data-cloud="${cloudId}">${n}件</button>`;
  }).join('');
  el.innerHTML = `<span class="count-label">表示件数:</span>${buttons}`;
  el.addEventListener('click', e => {
    const btn = e.target.closest('.count-btn');
    if (!btn) return;
    applyCount(btn.dataset.cloud, parseInt(btn.dataset.count));
  });
}

/** 指定件数でグリッドを再描画し、フィルター状態も復元する */
function applyCount(cloudId, count) {
  const grid = document.getElementById(`${cloudId}-grid`);
  if (!grid) return;

  const slice = (cloudItems[cloudId] || []).slice(0, count);
  grid.innerHTML = slice.map(item => renderCard(item)).join('');

  // アクティブなカテゴリフィルターを再適用
  const filterBar = document.getElementById(`${cloudId}-filter`);
  if (filterBar) {
    const activeBtn = filterBar.querySelector('.filter-btn.active');
    if (activeBtn && activeBtn.dataset.cat !== 'all') {
      const cat = activeBtn.dataset.cat;
      grid.querySelectorAll('.news-card').forEach(card => {
        card.style.display = card.dataset.category === cat ? '' : 'none';
      });
    }
  }

  // アニメーション
  if (window._cardObserver) {
    grid.querySelectorAll('.news-card').forEach(c => window._cardObserver.observe(c));
  } else {
    grid.querySelectorAll('.news-card').forEach(c => c.classList.add('visible'));
  }

  // 件数ボタンのアクティブ状態を更新
  const countEl = document.getElementById(`${cloudId}-count`);
  if (countEl) {
    countEl.querySelectorAll('.count-btn').forEach(btn => {
      btn.classList.toggle('active', parseInt(btn.dataset.count) === count);
    });
  }
}

/** メイン: JSON 読み込み → ソート → フィルターバー → カード描画 */
async function loadNews() {
  const CLOUD_IDS = ['azure', 'aws', 'gcp', 'oci'];

  try {
    const res = await fetch('data/news.json');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    // ヘッダーの更新日時を反映
    const updateEl = document.getElementById('update-date');
    if (updateEl && data.updated) {
      updateEl.textContent = `最終更新: ${data.updated}`;
    }
    const latestSub = document.getElementById('latest-updated-at');
    if (latestSub && data.updated) {
      latestSub.textContent = `データ更新: ${data.updated}`;
    }

    // 最新情報ハイライトセクション
    renderLatestSummary(data);

    for (const cloudId of CLOUD_IDS) {
      const grid = document.getElementById(`${cloudId}-grid`);
      if (!grid) continue;

      let items = (data.clouds && data.clouds[cloudId]) ? [...data.clouds[cloudId]] : [];

      if (items.length === 0) {
        grid.innerHTML = '<p class="grid-empty">現在、ニュースはありません。</p>';
        continue;
      }

      // 公開日降順ソート（最新が先頭）
      items.sort((a, b) => (b.date_iso || '').localeCompare(a.date_iso || ''));

      // 全アイテムをキャッシュ
      cloudItems[cloudId] = items;

      // フィルターバー構築（全件ベース）
      buildFilterBar(`${cloudId}-filter`, items, `${cloudId}-grid`);

      // 件数セレクター構築
      buildCountSelector(cloudId, items.length);

      // 初期描画（デフォルト件数）
      applyCount(cloudId, DEFAULT_COUNT);
    }

  } catch (err) {
    console.error('ニュースデータの読み込みに失敗しました:', err);
    ['azure', 'aws', 'gcp', 'oci'].forEach(cloudId => {
      const grid = document.getElementById(`${cloudId}-grid`);
      if (grid) {
        grid.innerHTML = '<p class="grid-error">データの読み込みに失敗しました。しばらくしてからページを更新してください。</p>';
      }
    });
  }
}

// DOM 構築後に実行
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', loadNews);
} else {
  loadNews();
}

