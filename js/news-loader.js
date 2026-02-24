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

// 各クラウドのメタ情報（公式SVGアイコン）
const CLOUD_META = {
  azure: { name: 'Azure', colorClass: 'azure', icon: 'https://cdn.simpleicons.org/microsoftazure/4da6ff' },
  aws:   { name: 'AWS',   colorClass: 'aws',   icon: 'https://cdn.simpleicons.org/amazonaws/ffaa33' },
  gcp:   { name: 'GCP',   colorClass: 'gcp',   icon: 'https://cdn.simpleicons.org/googlecloud/4ade80' },
  oci:   { name: 'OCI',   colorClass: 'oci',   icon: 'https://cdn.simpleicons.org/oracle/f87171' },
};

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

/** 最新情報ハイライトセクションを描画する */
function renderLatestSummary(data) {
  const grid = document.getElementById('latest-updates-grid');
  if (!grid) return;

  const cards = Object.entries(CLOUD_META).map(([cloudId, meta]) => {
    const rawItems = (data.clouds && data.clouds[cloudId]) ? [...data.clouds[cloudId]] : [];
    if (rawItems.length === 0) return '';

    // 最新一件を取得
    const sorted = rawItems.sort((a, b) => (b.date_iso || '').localeCompare(a.date_iso || ''));
    const latest = sorted[0];
    const cfg = TAG_CONFIG[latest.category] || { icon: '☁️', label: latest.cat_label || '' };

    return `
      <div class="latest-card latest-${meta.colorClass}">
        <div class="latest-cloud-badge">
          <img src="${meta.icon}" alt="${meta.name}" class="latest-cloud-icon" />
          <span class="latest-cloud-name">${meta.name}</span>
        </div>
        <div class="latest-cat">${cfg.icon} ${cfg.label}</div>
        <a href="${escHtml(latest.link)}" target="_blank" rel="noopener noreferrer" class="latest-title">${escHtml(latest.title)}</a>
        <div class="latest-date">${escHtml(latest.date)}</div>
      </div>`;
  });

  grid.innerHTML = cards.join('');
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

      // フィルターバー構築
      buildFilterBar(`${cloudId}-filter`, items, `${cloudId}-grid`);

      // カード描画
      grid.innerHTML = items.map(item => renderCard(item)).join('');

      // フェードインアニメーション
      if (window._cardObserver) {
        grid.querySelectorAll('.news-card').forEach(card => window._cardObserver.observe(card));
      } else {
        grid.querySelectorAll('.news-card').forEach(card => card.classList.add('visible'));
      }
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

