from __future__ import annotations

import argparse
import sys
from datetime import date

from .analysis import analyze
from .config import Config
from .db import Database
from .gsc import collect
from .report import render
from .telegram import send


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="burakakgul.com SEO feedback loop")
    commands = result.add_subparsers(dest="command", required=True)
    collect_parser = commands.add_parser("collect", help="collect finalized GSC data")
    collect_parser.add_argument("--days", type=int)
    collect_parser.add_argument("--end-date", type=_date)
    report_parser = commands.add_parser("report", help="create the weekly action report")
    report_parser.add_argument("--send", action="store_true", help="send through Telegram")
    commands.add_parser("doctor", help="check local configuration")
    return result


def doctor(config: Config, database: Database) -> int:
    checks = [
        ("GSC site", config.site_url),
        ("Credentials", "ready" if config.credentials_file.is_file() else f"missing: {config.credentials_file}"),
        ("Database", str(config.database_file)),
        ("Telegram token", "set" if config.telegram_token else "missing"),
        ("Telegram chat IDs", str(len(config.telegram_chat_ids))),
        ("Latest data", str(database.latest_day() or "none")),
    ]
    for name, value in checks:
        print(f"{name}: {value}")
    return 0 if config.credentials_file.is_file() else 2


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config = Config.from_env()
    database = Database(config.database_file)
    try:
        if args.command == "doctor":
            return doctor(config, database)
        if args.command == "collect":
            start, end, count = collect(config, database, args.days, args.end_date)
            print(f"Collected {count} rows for {start.isoformat()}..{end.isoformat()}")
            return 0
        if args.command == "report":
            message = render(analyze(database, config.min_impressions), config.report_top_n)
            print(message)
            if args.send:
                count = send(config, message)
                print(f"Sent to {count} Telegram chat(s)")
            return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        database.close()
    return 0
