# burakakgul.com SEO feedback loop

This service collects finalized Google Search Console data into SQLite and creates a short weekly action report. It never edits the website or creates pages.

## What it measures

- query, landing page, country and device dimensions
- clicks, impressions, CTR and impression-weighted average position
- queries ranking between positions 3 and 20
- CTR gaps relative to the site's own position buckets
- week-over-week click, impression and position declines
- conservative language/topic mismatches between a query and its landing page

CTR expectations blend the site's trailing 90-day data with a fallback position curve until each bucket has enough observations. This avoids applying one fixed CTR threshold to every rank.

Search Console cannot expose an individual's search query to Umami. The two sources therefore remain privacy-safe, aggregate signals: GSC explains discovery; Umami events explain what visitors do after arriving.

## Server layout

```text
/srv/seo-feedback/
├── current -> releases/<timestamp>/
├── data/search-console.sqlite3
├── logs/
├── secrets/gsc-service-account.json
└── vendor/
```

The release symlink makes rollback a single symlink change. Database, credentials and logs are outside each release.

## Google setup

1. Enable the Google Search Console API in a Google Cloud project.
2. Create a service account and download its JSON key.
3. Add the service account email as a user of the Search Console property.
4. Store the key as `/srv/seo-feedback/secrets/gsc-service-account.json` with mode `0600`.
5. Set `GSC_SITE_URL` to the exact property identifier. The default is `sc-domain:burakakgul.com`; a URL-prefix property would look like `https://burakakgul.com/`.

The collector uses Google's recommended service-account client libraries and the official 25,000-row pagination limit.

## Commands

```sh
/srv/seo-feedback/current/run doctor
/srv/seo-feedback/current/run collect
/srv/seo-feedback/current/run report
/srv/seo-feedback/current/run report --send
```

The first collection backfills 35 finalized days. Later runs refresh the last 10 finalized days, making delayed corrections idempotent. Search Console's newest three calendar days are deliberately skipped.

`report --send` reuses the existing `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_IDS` variables from root's crontab. Secrets are never copied into this project.

## Proposed cron block for `izmirgli`

The existing crontab must be backed up and diffed before this block is appended.

```cron
# === WEB SİTESİ / SEO ===
20 4 * * 2-7 /srv/crypto/bin/withlock.sh seo_gsc 45 sh -c 'cd /srv/seo-feedback/current && ./run collect >> /srv/seo-feedback/logs/collect.log 2>&1'
20 4 * * 1 /srv/crypto/bin/withlock.sh seo_gsc 60 sh -c 'cd /srv/seo-feedback/current && ./run collect >> /srv/seo-feedback/logs/collect.log 2>&1 && ./run report --send >> /srv/seo-feedback/logs/weekly.log 2>&1'
```

This runs away from the current 21:50 Umami job, 00:02 backup and 03:00 crypto jobs. Both SEO jobs use the same lock name, so two SEO processes cannot overlap.

## Environment overrides

```text
GSC_SITE_URL=sc-domain:burakakgul.com
GSC_CREDENTIALS_FILE=/srv/seo-feedback/secrets/gsc-service-account.json
SEO_DATABASE_FILE=/srv/seo-feedback/data/search-console.sqlite3
SEO_REPORT_TOP_N=3
SEO_MIN_IMPRESSIONS=10
```

The low minimum only controls when a query becomes eligible for analysis. Opportunity ranking still weighs impression volume, position and the position-relative CTR gap.
