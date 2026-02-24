// CloudWatch JP — main.js

// スムーススクロール（ナビリンク）
document.querySelectorAll('.nav-link[href^="#"]').forEach(link => {
  link.addEventListener('click', e => {
    e.preventDefault();
    const target = document.querySelector(link.getAttribute('href'));
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
});

// サマリーカードのスクロール
function scrollTo(id) {
  const el = document.getElementById(id);
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// アクティブナビゲーション（スクロールに応じてハイライト）
const sections = document.querySelectorAll('section[id]');
const navLinks = document.querySelectorAll('.nav-link[href^="#"]');

const observer = new IntersectionObserver(
  entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        navLinks.forEach(link => {
          link.classList.remove('active');
          if (link.getAttribute('href') === '#' + entry.target.id) {
            link.classList.add('active');
          }
        });
      }
    });
  },
  { rootMargin: '-20% 0px -70% 0px' }
);

sections.forEach(s => observer.observe(s));

// ニュースカードのフェードインアニメーション
const cardObserver = new IntersectionObserver(
  entries => {
    entries.forEach((entry, i) => {
      if (entry.isIntersecting) {
        setTimeout(() => {
          entry.target.classList.add('visible');
        }, i * 60);
        cardObserver.unobserve(entry.target);
      }
    });
  },
  { threshold: 0.08 }
);

document.querySelectorAll('.news-card, .summary-card').forEach(card => {
  card.classList.add('fade-in');
  cardObserver.observe(card);
});

// テスト: コンソールに読み込み完了を表示
console.log('%c☁ CloudWatch JP — Loaded', 'color: #60a5fa; font-weight: bold; font-size: 14px;');
