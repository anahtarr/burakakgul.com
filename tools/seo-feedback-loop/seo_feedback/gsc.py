from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from .config import Config
from .db import Database


SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
DIMENSIONS = ["date", "query", "page", "country", "device"]
PAGE_SIZE = 25_000


def build_service(config: Config) -> Any:
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Google API libraries are missing; install requirements.txt first."
        ) from exc

    if not config.credentials_file.is_file():
        raise RuntimeError(f"Credentials file not found: {config.credentials_file}")

    credentials = service_account.Credentials.from_service_account_file(
        config.credentials_file, scopes=SCOPES
    )
    return build("searchconsole", "v1", credentials=credentials, cache_discovery=False)


def fetch_day(service: Any, site_url: str, day: date) -> list[dict]:
    rows: list[dict] = []
    start_row = 0
    while True:
        body = {
            "startDate": day.isoformat(),
            "endDate": day.isoformat(),
            "dimensions": DIMENSIONS,
            "type": "web",
            "dataState": "final",
            "aggregationType": "auto",
            "rowLimit": PAGE_SIZE,
            "startRow": start_row,
        }
        response = (
            service.searchanalytics()
            .query(siteUrl=site_url, body=body)
            .execute(num_retries=3)
        )
        page = response.get("rows", [])
        for item in page:
            keys = item.get("keys", [])
            if len(keys) != len(DIMENSIONS):
                continue
            rows.append(
                {
                    "query": keys[1],
                    "page": keys[2],
                    "country": keys[3],
                    "device": keys[4],
                    "clicks": item.get("clicks", 0),
                    "impressions": item.get("impressions", 0),
                    "ctr": item.get("ctr", 0),
                    "position": item.get("position", 0),
                }
            )
        if len(page) < PAGE_SIZE:
            break
        start_row += PAGE_SIZE
    return rows


def collect(config: Config, database: Database, days: int | None, end_day: date | None) -> tuple[date, date, int]:
    effective_end = end_day or (date.today() - timedelta(days=3))
    effective_days = days if days is not None else (35 if not database.has_data() else 10)
    if effective_days < 1:
        raise ValueError("days must be positive")
    start_day = effective_end - timedelta(days=effective_days - 1)
    service = build_service(config)
    total = 0
    cursor = start_day
    try:
        while cursor <= effective_end:
            day_rows = fetch_day(service, config.site_url, cursor)
            total += database.replace_day(cursor, day_rows)
            cursor += timedelta(days=1)
    except Exception:
        database.record_run(
            datetime.now(timezone.utc).isoformat(), start_day, effective_end, total, "failed"
        )
        raise
    database.record_run(
        datetime.now(timezone.utc).isoformat(), start_day, effective_end, total, "ok"
    )
    return start_day, effective_end, total
