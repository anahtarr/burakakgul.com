# burakakgul.com SEO feedback loop

This service runs on Atlas. It keeps the existing finalized Google Search Console collection and weekly report, and adds a conservative, auditable optimization cycle for the existing site. It never creates a page, URL or blog post.

## Safety policy

- At most one change per calendar week.
- A query normally needs at least 100 impressions and 14 active days in the trailing 28 days.
- Candidates are limited to average positions 3–20 and are scored using position-relative expected CTR, CTR gap, stability and landing-page match.
- Deterministic filters run first. Gemini sees only the strongest final candidate and has a one-call weekly budget.
- Only the existing title or meta description may be changed automatically. The three language pages, visible content, design, responsive layout, analytics and site behavior remain intact.
- AI output is rejected if it contains HTML, exceeds length limits, introduces unverified vocabulary/facts, or touches a forbidden area.
- Low confidence, low volume, quota exhaustion, missing configuration or any failed check produces a safe no-op report.
- The same field has a 56-day cooldown.

## Server layout

```text
/srv/seo-feedback/
├── current -> releases/<timestamp>/
├── releases/
├── backups/
├── data/search-console.sqlite3
├── logs/
├── secrets/
│   ├── gsc-service-account.json
│   └── runtime.env
└── vendor/
```

The site source is the GitHub repository checked out at `/srv/seo-feedback-source`. Changes are versioned there and deployed by the existing GitHub/Netlify flow; production files are never edited in place.

## Commands

```sh
/srv/seo-feedback/current/run doctor
/srv/seo-feedback/current/run collect
/srv/seo-feedback/current/run report --send
/srv/seo-feedback/current/run-auto doctor
/srv/seo-feedback/current/run-auto dry-run
/srv/seo-feedback/current/run-auto weekly --send
```

Search Console's newest three calendar days are deliberately skipped. The first collection backfills 35 finalized days; later runs refresh the last 10 finalized days.

## Atlas cron

Keep the established collection/report schedule and add the weekly optimizer at a separate time:

```cron
15 22 * * 1-6 /usr/bin/flock -n /run/lock/seo-feedback-collect.lock /srv/seo-feedback/run collect >> /srv/seo-feedback/logs/collect.log 2>&1
15 22 * * 0 /usr/bin/flock -n /run/lock/seo-feedback-collect.lock sh -c '/srv/seo-feedback/run collect >> /srv/seo-feedback/logs/collect.log 2>&1 && /srv/seo-feedback/run report --send >> /srv/seo-feedback/logs/weekly.log 2>&1'
35 23 * * 0 /usr/bin/flock -n /run/lock/seo-feedback-auto.lock /srv/seo-feedback/current/run-auto weekly --send >> /srv/seo-feedback/logs/automation.log 2>&1
```

The 23:35 optimizer is separated from Atlas collection and from Gli_Izmir's 07:20/13:20/19:20 YouTube AI cycles. Gli_Izmir's five-minute reconcile-only job stays AI-free.

## Gemini budget and configuration

Gemini is optional and fail-closed. Put configuration in `/srv/seo-feedback/secrets/runtime.env` with mode `0600`; never commit it:

```text
GEMINI_API_KEY=...
SEO_GEMINI_MODEL=gemini-3.1-flash-lite
SEO_GEMINI_WEEKLY_BUDGET=1
```

The automation caches identical decisions, records usage locally, deduplicates prompts, applies exponential backoff, and treats quota exhaustion as “no change”. Defaults may be overridden with `SEO_AUTO_MIN_IMPRESSIONS`, `SEO_AUTO_MIN_ACTIVE_DAYS`, `SEO_AUTO_CONFIDENCE`, `SEO_AUTO_COOLDOWN_DAYS` and `SEO_AUTO_MEASURE_DAYS`.

## Change ledger and rollback

Every applied experiment is stored in SQLite table `seo_changes` with the target query, old/new value, baseline metrics, backup path and Git commit/release identifiers. The result is first evaluated after 14 days. Fewer than 60 post-change impressions is inconclusive and keeps the change. A significant CTR and position regression triggers an automatic Git revert and redeploy.

Before a push, the automation builds and checks all three languages, canonical/hreflang, JSON-LD, title/description limits and the Umami loader. After deploy it verifies HTTP, live DOM/meta and Umami. Any failure rolls the commit back automatically. The pre-change source snapshot is also kept under `/srv/seo-feedback/backups`.
