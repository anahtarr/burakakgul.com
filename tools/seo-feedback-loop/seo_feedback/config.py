from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default)).expanduser().resolve()


@dataclass(frozen=True)
class Config:
    site_url: str
    credentials_file: Path
    database_file: Path
    telegram_token: str | None
    telegram_chat_ids: tuple[str, ...]
    report_top_n: int
    min_impressions: int

    @classmethod
    def from_env(cls) -> "Config":
        chat_ids = tuple(
            value.strip()
            for value in os.environ.get("TELEGRAM_CHAT_IDS", "").split(",")
            if value.strip()
        )
        return cls(
            site_url=os.environ.get("GSC_SITE_URL", "sc-domain:burakakgul.com"),
            credentials_file=_path(
                "GSC_CREDENTIALS_FILE",
                "/srv/seo-feedback/secrets/gsc-service-account.json",
            ),
            database_file=_path(
                "SEO_DATABASE_FILE", "/srv/seo-feedback/data/search-console.sqlite3"
            ),
            telegram_token=os.environ.get("TELEGRAM_BOT_TOKEN"),
            telegram_chat_ids=chat_ids,
            report_top_n=max(1, int(os.environ.get("SEO_REPORT_TOP_N", "3"))),
            min_impressions=max(1, int(os.environ.get("SEO_MIN_IMPRESSIONS", "10"))),
        )
