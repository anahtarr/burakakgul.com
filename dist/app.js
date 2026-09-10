'use strict';
// Track all three production language routes; exclude local and staging hosts.
const analyticsEnabled = true;
if (analyticsEnabled && ['burakakgul.com', 'www.burakakgul.com'].includes(location.hostname)) {
  const script = document.createElement('script');
  script.src = 'https://cloud.umami.is/script.js';
  script.dataset.websiteId = '29731f47-29f2-43cc-995b-555807a6f476';
  script.defer = true;
  document.head.append(script);
  document.querySelectorAll('[data-social]').forEach(link => {
    link.addEventListener('click', () => window.umami?.track('social-click', {
      platform: link.dataset.social, language: document.documentElement.lang
    }));
  });
}
// Preserve a reader's position within the about section when changing languages.
document.querySelectorAll('.languages a').forEach(link => {
  if (location.hash) link.hash = location.hash;
});
