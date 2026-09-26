'use strict';
// Track all three production language routes; exclude local and staging hosts.
const analyticsEnabled = true;
if (analyticsEnabled && ['burakakgul.com', 'www.burakakgul.com'].includes(location.hostname)) {
  const language = document.documentElement.lang;
  const instagramLink = document.querySelector('[data-social="Instagram"]');
  if (instagramLink) {
    instagramLink.dataset.umamiEvent = 'instagram-click';
    instagramLink.dataset.umamiEventPlatform = 'Instagram';
    instagramLink.dataset.umamiEventLanguage = language;
  }

  document.querySelectorAll('[data-social]').forEach(link => {
    if (link === instagramLink) return;

    const isEmail = link.dataset.social === 'Email';
    link.dataset.umamiEvent = isEmail ? 'contact-click' : 'social-click';
    link.dataset.umamiEventLanguage = language;
    if (isEmail) {
      link.dataset.umamiEventMethod = 'email';
    } else {
      link.dataset.umamiEventPlatform = link.dataset.social;
    }
  });

  document.querySelectorAll('.languages a:not([aria-current="page"])').forEach(link => {
    link.dataset.umamiEvent = 'language-change';
    link.dataset.umamiEventFrom = language;
    link.dataset.umamiEventTo = link.lang;
  });

  const script = document.createElement('script');
  script.src = 'https://cloud.umami.is/script.js';
  script.dataset.websiteId = '29731f47-29f2-43cc-995b-555807a6f476';
  script.defer = true;
  document.head.append(script);

  const pendingEvents = [];
  const track = (name, data) => {
    if (window.umami?.track) {
      window.umami.track(name, data);
    } else {
      pendingEvents.push([name, data]);
    }
  };
  script.addEventListener('load', () => {
    while (pendingEvents.length && window.umami?.track) {
      window.umami.track(...pendingEvents.shift());
    }
  });

  const trackedDepths = new Set();
  let scrollTicking = false;
  const measureScrollDepth = () => {
    const scrollable = document.documentElement.scrollHeight - window.innerHeight;
    const depth = scrollable <= 0 ? 100 : ((window.scrollY / scrollable) * 100);
    [50, 90].forEach(mark => {
      if (depth >= mark && !trackedDepths.has(mark)) {
        trackedDepths.add(mark);
        track('scroll-depth', { depth: mark, language });
      }
    });
    scrollTicking = false;
  };
  addEventListener('scroll', () => {
    if (!scrollTicking) {
      scrollTicking = true;
      requestAnimationFrame(measureScrollDepth);
    }
  }, { passive: true });
  measureScrollDepth();

  const aboutSection = document.querySelector('.about');
  if (aboutSection && 'IntersectionObserver' in window) {
    const aboutObserver = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting && entry.intersectionRatio >= 0.35)) {
        track('about-view', { language });
        aboutObserver.disconnect();
      }
    }, { threshold: 0.35 });
    aboutObserver.observe(aboutSection);
  }
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
