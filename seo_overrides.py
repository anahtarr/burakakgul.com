"""Apply reviewed, machine-managed SEO metadata overrides after the static build."""
from __future__ import annotations

import html
import json
import re
from pathlib import Path


FILES = {"tr": "dist/index.html", "en": "dist/en/index.html", "de": "dist/de/index.html"}


def apply(repo: Path) -> None:
    path = repo / "seo-overrides.json"
    if not path.is_file():
        return
    overrides = json.loads(path.read_text())
    if not isinstance(overrides, dict):
        raise ValueError("seo-overrides.json must contain an object")
    for language, fields in overrides.items():
        if language not in FILES or not isinstance(fields, dict):
            raise ValueError("unsupported SEO override language")
        unknown = set(fields) - {"title", "description"}
        if unknown:
            raise ValueError(f"unsupported SEO override fields: {sorted(unknown)}")
        target = repo / FILES[language]
        text = target.read_text()
        if "title" in fields:
            value = str(fields["title"])
            if not 20 <= len(value) <= 65 or any(c in value for c in "<>"):
                raise ValueError("unsafe title override")
            text, count = re.subn(r"<title>.*?</title>", f"<title>{html.escape(value)}</title>", text,
                                  count=1, flags=re.I | re.S)
            if count != 1:
                raise ValueError("title target missing or ambiguous")
        if "description" in fields:
            value = str(fields["description"])
            if not 50 <= len(value) <= 165 or any(c in value for c in "<>"):
                raise ValueError("unsafe description override")
            replacement = f'<meta name="description" content="{html.escape(value, quote=True)}"'
            text, count = re.subn(r'<meta\s+name="description"\s+content="[^"]*"', replacement, text,
                                  count=1, flags=re.I)
            if count != 1:
                raise ValueError("description target missing or ambiguous")
        target.write_text(text)


if __name__ == "__main__":
    apply(Path(__file__).resolve().parent)
