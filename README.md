# burakakgul.com

Burak Akgül’s personal website, in Turkish, English and German.

Native HTML, CSS and JavaScript. Fonts and images are served locally.

## Site structure

- `dist/index.html`: Turkish
- `dist/en/index.html`: English
- `dist/de/index.html`: German
- `dist/assets/`: images, icons and fonts
- `build.py`: regenerates the static language pages and SEO files using Python 3 (standard library only)
- `profile.json`: structured profile information
- `netlify.toml`: publishing directory and legacy URL redirects
- `tools/seo-feedback-loop/`: separately deployed, read-only Search Console reporting worker

Run `python3 build.py` after editing content, then serve `dist` with a static HTTP server. Netlify publishes the committed `dist` directory; no build service or package installation is required.

## Analytics

All three language routes use the existing Umami website ID. Tracking runs only on `burakakgul.com` and `www.burakakgul.com`, never on localhost or staging hosts. Route-level page views distinguish `/`, `/en/`, and `/de/`.

Custom events are intentionally small and stable:

- `instagram-click` preserves the existing Instagram event name
- `social-click` includes platform and language
- `contact-click` identifies the email contact action
- `language-change` includes the source and destination languages
- `about-view` fires once after a meaningful part of the About section is visible
- `scroll-depth` fires once at 50% and once at 90%

## Repository boundaries

This repository contains the website and its SEO reporting worker. The worker is deployed separately and never ships in `dist`. Credentials, collected analytics data and generated reports remain on the server and are excluded from Git. Public market snapshots belong in `crypto-feed`; private research remains in `crypto-private`.
