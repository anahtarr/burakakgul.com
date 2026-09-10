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

Run `python3 build.py` after editing content, then serve `dist` with a static HTTP server. Netlify publishes the committed `dist` directory; no build service or package installation is required.

## Analytics

All three language routes use the existing Umami website ID. Tracking runs only on `burakakgul.com` and `www.burakakgul.com`, never on localhost or staging hosts. Social clicks include platform and language. Route-level page views distinguish `/`, `/en/`, and `/de/`.

## Repository boundaries

This repository contains the website only. Public market snapshots belong in `crypto-feed`; private research remains in `crypto-private`. Neither credentials nor market snapshot publishing jobs belong here.
