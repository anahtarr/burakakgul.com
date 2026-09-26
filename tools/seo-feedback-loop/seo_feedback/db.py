from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import date
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS search_performance (
    day TEXT NOT NULL,
    query TEXT NOT NULL,
    page TEXT NOT NULL,
    country TEXT NOT NULL,
    device TEXT NOT NULL,
    clicks REAL NOT NULL,
    impressions REAL NOT NULL,
    ctr REAL NOT NULL,
    position REAL NOT NULL,
    PRIMARY KEY (day, query, page, country, device)
);
CREATE INDEX IF NOT EXISTS idx_search_performance_day
    ON search_performance(day);
CREATE INDEX IF NOT EXISTS idx_search_performance_query_day
    ON search_performance(query, day);
CREATE TABLE IF NOT EXISTS collection_runs (
    collected_at TEXT NOT NULL,
    start_day TEXT NOT NULL,
    end_day TEXT NOT NULL,
    rows_written INTEGER NOT NULL,
    status TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)

    def close(self) -> None:
        self.connection.close()

    def replace_day(self, day: date, rows: Iterable[dict]) -> int:
        prepared = [
            (
                day.isoformat(),
                row["query"],
                row["page"],
                row["country"],
                row["device"],
                float(row["clicks"]),
                float(row["impressions"]),
                float(row["ctr"]),
                float(row["position"]),
            )
            for row in rows
        ]
        with self.connection:
            self.connection.execute(
                "DELETE FROM search_performance WHERE day = ?", (day.isoformat(),)
            )
            self.connection.executemany(
                """
                INSERT INTO search_performance (
                    day, query, page, country, device,
                    clicks, impressions, ctr, position
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                prepared,
            )
        return len(prepared)

    def latest_day(self) -> date | None:
        row = self.connection.execute(
            "SELECT MAX(day) AS latest FROM search_performance"
        ).fetchone()
        return date.fromisoformat(row["latest"]) if row and row["latest"] else None

    def has_data(self) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM search_performance LIMIT 1"
        ).fetchone()
        return row is not None

    def record_run(
        self, collected_at: str, start_day: date, end_day: date, rows: int, status: str
    ) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO collection_runs
                    (collected_at, start_day, end_day, rows_written, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (collected_at, start_day.isoformat(), end_day.isoformat(), rows, status),
            )

    def aggregate(self, start_day: date, end_day: date) -> list[sqlite3.Row]:
        return list(
            self.connection.execute(
                """
                SELECT
                    query,
                    page,
                    SUM(clicks) AS clicks,
                    SUM(impressions) AS impressions,
                    CASE WHEN SUM(impressions) > 0
                         THEN SUM(clicks) / SUM(impressions) ELSE 0 END AS ctr,
                    CASE WHEN SUM(impressions) > 0
                         THEN SUM(position * impressions) / SUM(impressions)
                         ELSE 0 END AS position
                FROM search_performance
                WHERE day BETWEEN ? AND ?
                GROUP BY query, page
                """,
                (start_day.isoformat(), end_day.isoformat()),
            )
        )

    def ctr_baseline(self, start_day: date, end_day: date) -> list[sqlite3.Row]:
        return list(
            self.connection.execute(
                """
                SELECT
                    CASE
                        WHEN position < 1.5 THEN '1'
                        WHEN position < 2.5 THEN '2'
                        WHEN position < 3.5 THEN '3'
                        WHEN position < 5.5 THEN '4-5'
                        WHEN position < 10.5 THEN '6-10'
                        WHEN position < 20.5 THEN '11-20'
                        ELSE '21+'
                    END AS position_bucket,
                    SUM(clicks) AS clicks,
                    SUM(impressions) AS impressions
                FROM search_performance
                WHERE day BETWEEN ? AND ?
                GROUP BY position_bucket
                """,
                (start_day.isoformat(), end_day.isoformat()),
            )
        )
