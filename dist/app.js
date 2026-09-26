'use strict';
// Track all three production language routes; exclude local and staging hosts.
const analyticsEnabled = true;
if (analyticsEnabled && ['burakakgul.com', 'www.burakakgul.com'].includes(location.hostname)) {
  const instagramLink = document.querySelector('[data-social="Instagram"]');
  if (instagramLink) {
    instagramLink.dataset.umamiEvent = 'instagram-click';
    instagramLink.dataset.umamiEventPlatform = 'Instagram';
    instagramLink.dataset.umamiEventLanguage = document.documentElement.lang;
  }

  const script = document.createElement('script');
  script.src = 'https://cloud.umami.is/script.js';
  script.dataset.websiteId = '29731f47-29f2-43cc-995b-555807a6f476';
  script.defer = true;
  document.head.append(script);
  document.querySelectorAll('[data-social]').forEach(link => {
    if (link.hasAttribute('data-umami-event')) return;

    link.addEventListener('click', () => window.umami?.track('social-click', {
      platform: link.dataset.social, language: document.documentElement.lang
    }));
  });
}
// Preserve a reader's position within the about section when changing languages.
document.querySelectorAll('.languages a').forEach(link => {
  if (location.hash) link.hash = location.hash;
});

// Any visible part reveals the section, including reloads near the quote.
const aboutInner = document.querySelector('.about-inner');
const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
if (aboutInner && !motionPreference.matches && 'IntersectionObserver' in window) {
  const reveal = () => {
    aboutInner.classList.remove('about-pending');
    aboutInner.classList.add('about-visible');
  };
  const observer = new IntersectionObserver(entries => {
    if (entries.some(entry => entry.isIntersecting)) {
      reveal();
      observer.disconnect();
    }
  }, { threshold: 0, rootMargin: '0px 0px -24px 0px' });
  aboutInner.classList.add('about-pending');
  observer.observe(aboutInner);
  motionPreference.addEventListener('change', event => {
    if (event.matches) {
      reveal();
      observer.disconnect();
    }
  });
}
