from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from .config import Config
from .db import Database


SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
DIMENSIONS = ["date", "query", "page", "country", "device"]
PAGE_SIZE = 25_000


def build_session(config: Config) -> Any:
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
    except ImportError as exc:
        raise RuntimeError(
            "Google authentication libraries are missing; install requirements.txt first."
        ) from exc

    if not config.credentials_file.is_file():
        raise RuntimeError(f"Credentials file not found: {config.credentials_file}")

    credentials = service_account.Credentials.from_service_account_file(
        config.credentials_file, scopes=SCOPES
    )
    return AuthorizedSession(credentials)


def _request_page(session: Any, endpoint: str, body: dict) -> dict:
    for attempt in range(4):
        response = session.post(endpoint, json=body, timeout=45)
        if response.status_code not in {429, 500, 502, 503, 504}:
            response.raise_for_status()
            return response.json()
        if attempt < 3:
            time.sleep(2**attempt)
    response.raise_for_status()
    return {}


def fetch_day(session: Any, site_url: str, day: date) -> list[dict]:
    rows: list[dict] = []
    start_row = 0
    encoded_site = quote(site_url, safe="")
    endpoint = (
        "https://www.googleapis.com/webmasters/v3/sites/"
        f"{encoded_site}/searchAnalytics/query"
    )
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
        response = _request_page(session, endpoint, body)
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
    session = build_session(config)
    total = 0
    cursor = start_day
    try:
        while cursor <= effective_end:
            day_rows = fetch_day(session, config.site_url, cursor)
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
