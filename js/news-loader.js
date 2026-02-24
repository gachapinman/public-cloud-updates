/**
 * news-loader.js
 * data/news.json を取得して各クラウドのニュースグリッドを動的レンダリングする
 */

const TAG_CLASSES = {
  'ai-tag':        'ai-tag',
  'security-tag':  'security-tag',
  'container-tag': 'container-tag',
  'database-tag':  'database-tag',
  'storage-tag':   'storage-tag',
  'network-tag':   'network-tag',
  'compute-tag':   'compute-tag',
};

function renderCard(item, isFeatured) {
  const featuredClass = isFeatured ? ' featured' : '';
  const tagClass = TAG_CLASSES[item.tag] || item.tag || 'compute-tag';

  return `
    <article class="news-card${featuredClass} fade-in">
      <div class="news-category ${tagClass}">${item.cat_label}</div>
      <h3 class="news-title">
        <a href="${escHtml(item.link)}" target="_blank" rel="noopener noreferrer">${escHtml(item.title)}</a>
      </h3>
      <p class="news-summary">${escHtml(item.summary)}</p>
      <div class="news-meta">
        <time datetime="${escHtml(item.date_iso)}">${escHtml(item.date)}</time>
        ${item.category ? `<span class="news-category-label">${escHtml(item.category)}</span>` : ''}
        <a href="${escHtml(item.link)}" target="_blank" rel="noopener noreferrer" class="news-read-more">元記事を見る →</a>
      </div>
    </article>`;
}

function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

async function loadNews() {
  const CLOUD_IDS = ['azure', 'aws', 'gcp', 'oci'];

  try {
    const res = await fetch('data/news.json');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    // 更新日時をヘッダーに反映
    const updateEl = document.getElementById('update-date');
    if (updateEl && data.updated) {
      updateEl.textContent = `最終更新: ${data.updated}`;
    }

    // 各クラウドのグリッドにカードをレンダリング
    for (const cloudId of CLOUD_IDS) {
      const grid = document.getElementById(`${cloudId}-grid`);
      if (!grid) continue;

      const items = data.clouds[cloudId];
      if (!items || items.length === 0) {
        grid.innerHTML = '<p class="grid-empty">現在、ニュースはありません。</p>';
        continue;
      }

      grid.innerHTML = items.map((item, i) => renderCard(item, i === 0)).join('');

      // IntersectionObserver でフェードインを適用
      if (window._cardObserver) {
        grid.querySelectorAll('.news-card').forEach(card => {
          window._cardObserver.observe(card);
        });
      } else {
        // main.js の Observer がまだ未設定の場合は即表示
        grid.querySelectorAll('.news-card').forEach(card => {
          card.classList.add('visible');
        });
      }
    }

  } catch (err) {
    console.error('ニュースデータの読み込みに失敗しました:', err);
    // エラー時はすべてのグリッドにメッセージを表示
    CLOUD_IDS.forEach(cloudId => {
      const grid = document.getElementById(`${cloudId}-grid`);
      if (grid && grid.querySelector('.grid-loading')) {
        grid.innerHTML = '<p class="grid-error">データの読み込みに失敗しました。しばらくしてからページを更新してください。</p>';
      }
    });
  }
}

// DOM 読み込み後に実行
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', loadNews);
} else {
  loadNews();
}
