from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tarfile
import time
import unicodedata
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path


DB = Path(os.getenv("SEO_DATABASE_FILE", "/srv/seo-feedback/data/search-console.sqlite3"))
REPO = Path(os.getenv("SEO_SITE_REPO", "/srv/seo-feedback-source"))
BACKUPS = Path(os.getenv("SEO_BACKUP_DIR", "/srv/seo-feedback/backups"))
RUNTIME_ENV = Path(os.getenv("SEO_RUNTIME_ENV", "/srv/seo-feedback/secrets/runtime.env"))
MODEL = os.getenv("SEO_GEMINI_MODEL", "gemini-3.1-flash-lite")
MIN_IMPRESSIONS = int(os.getenv("SEO_AUTO_MIN_IMPRESSIONS", "100"))
MIN_DAYS = int(os.getenv("SEO_AUTO_MIN_DAYS", "14"))
MIN_CONFIDENCE = float(os.getenv("SEO_AUTO_MIN_CONFIDENCE", "0.78"))
COOLDOWN_DAYS = int(os.getenv("SEO_AUTO_COOLDOWN_DAYS", "56"))
WEEKLY_LIMIT = 1
LANG_BY_PATH = {"/": "tr", "/en/": "en", "/de/": "de"}
DIST_BY_LANG = {"tr": "dist/index.html", "en": "dist/en/index.html", "de": "dist/de/index.html"}
ALLOWED_FIELDS = {"title", "description"}
FORBIDDEN = re.compile(r"(?i)\b(new page|blog|url|script|style|tracking|umami|job|employer|aselsan|award|degree|university)\b")


@dataclass
class Candidate:
    query: str
    page: str
    language: str
    impressions: float
    clicks: float
    ctr: float
    position: float
    expected_ctr: float
    active_days: int
    position_sd: float
    confidence: float


def env_values() -> dict[str, str]:
    values = dict(os.environ)
    if RUNTIME_ENV.is_file():
        for raw in RUNTIME_ENV.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return values


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    con.executescript("""
    CREATE TABLE IF NOT EXISTS seo_changes(
      id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, query TEXT NOT NULL,
      page TEXT NOT NULL, language TEXT NOT NULL, field TEXT NOT NULL,
      old_value TEXT NOT NULL, new_value TEXT NOT NULL, baseline_json TEXT NOT NULL,
      confidence REAL NOT NULL, model TEXT, prompt_hash TEXT, backup_path TEXT,
      commit_before TEXT, commit_after TEXT, deploy_url TEXT, status TEXT NOT NULL,
      evaluate_after TEXT NOT NULL, evaluated_at TEXT, outcome TEXT,
      rollback_commit TEXT, notes TEXT
    );
    CREATE TABLE IF NOT EXISTS seo_ai_cache(
      prompt_hash TEXT PRIMARY KEY, model TEXT NOT NULL, response_json TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS seo_ai_usage(
      id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, model TEXT NOT NULL,
      prompt_hash TEXT NOT NULL, result TEXT NOT NULL, prompt_tokens INTEGER DEFAULT 0
    );
    """)
    con.commit()
    return con


def expected_ctr(position: float) -> float:
    curve = [(1, .285), (2, .157), (3, .110), (4, .075), (5, .055), (6, .041),
             (7, .033), (8, .027), (9, .023), (10, .020), (12, .015), (15, .011), (20, .007)]
    for (p1, c1), (p2, c2) in zip(curve, curve[1:]):
        if p1 <= position <= p2:
            return c1 + (c2 - c1) * (position - p1) / (p2 - p1)
    return curve[0][1] if position < 1 else curve[-1][1]


def candidates(con: sqlite3.Connection) -> list[Candidate]:
    latest = con.execute("SELECT MAX(day) FROM search_performance").fetchone()[0]
    if not latest:
        return []
    end = dt.date.fromisoformat(latest)
    start = end - dt.timedelta(days=27)
    rows = con.execute("""
      SELECT query,page,SUM(clicks) clicks,SUM(impressions) impressions,
             CASE WHEN SUM(impressions)>0 THEN SUM(clicks)/SUM(impressions) ELSE 0 END ctr,
             SUM(position*impressions)/NULLIF(SUM(impressions),0) position,
             COUNT(DISTINCT day) active_days
      FROM search_performance WHERE day BETWEEN ? AND ?
      GROUP BY query,page HAVING SUM(impressions)>=?
    """, (start.isoformat(), end.isoformat(), MIN_IMPRESSIONS)).fetchall()
    out: list[Candidate] = []
    for row in rows:
        page = urllib.request.url2pathname(row["page"] or "/")
        if page.startswith("http"):
            from urllib.parse import urlparse
            page = urlparse(page).path or "/"
        if page not in LANG_BY_PATH or row["active_days"] < MIN_DAYS or not (3 <= row["position"] <= 20):
            continue
        daily = con.execute("""
          SELECT SUM(position*impressions)/NULLIF(SUM(impressions),0) p
          FROM search_performance WHERE query=? AND page LIKE ? AND day BETWEEN ? AND ?
          GROUP BY day HAVING SUM(impressions)>0
        """, (row["query"], "%" + page, start.isoformat(), end.isoformat())).fetchall()
        vals = [float(x[0]) for x in daily if x[0] is not None]
        mean = sum(vals) / len(vals) if vals else float(row["position"])
        sd = (sum((x - mean) ** 2 for x in vals) / len(vals)) ** .5 if vals else 99.0
        exp = expected_ctr(float(row["position"]))
        gap = exp - float(row["ctr"])
        stability = max(0.0, 1.0 - sd / 4.0)
        volume = min(1.0, float(row["impressions"]) / 250.0)
        history = min(1.0, int(row["active_days"]) / 21.0)
        gap_score = min(1.0, max(0.0, gap / max(exp, .01)))
        confidence = .30 * volume + .25 * history + .25 * stability + .20 * gap_score
        if gap >= .015 and confidence >= MIN_CONFIDENCE:
            out.append(Candidate(row["query"], page, LANG_BY_PATH[page], float(row["impressions"]),
                                 float(row["clicks"]), float(row["ctr"]), float(row["position"]),
                                 exp, int(row["active_days"]), sd, confidence))
    return sorted(out, key=lambda x: (x.confidence, x.impressions * (x.expected_ctr - x.ctr)), reverse=True)[:3]


def current_meta(language: str) -> dict[str, str]:
    text = (REPO / DIST_BY_LANG[language]).read_text()
    title = re.search(r"<title>(.*?)</title>", text, re.I | re.S)
    desc = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', text, re.I)
    if not title or not desc:
        raise RuntimeError("title/description missing from generated page")
    return {"title": html.unescape(title.group(1).strip()), "description": html.unescape(desc.group(1).strip())}


def normalized_words(value: str) -> set[str]:
    value = unicodedata.normalize("NFKD", value).casefold()
    return set(re.findall(r"[a-z0-9çğıöşü]+", value))


def validate_proposal(candidate: Candidate, field: str, before: str, after: str) -> None:
    if field not in ALLOWED_FIELDS or before == after or "<" in after or ">" in after:
        raise ValueError("proposal changes a forbidden field or contains markup")
    limits = (20, 65) if field == "title" else (50, 165)
    if not limits[0] <= len(after) <= limits[1]:
        raise ValueError("proposal length outside safe limits")
    if FORBIDDEN.search(after):
        raise ValueError("proposal contains a forbidden claim/change")
    page_text = re.sub(r"<[^>]+>", " ", (REPO / DIST_BY_LANG[candidate.language]).read_text())
    allowed = normalized_words(page_text + " " + candidate.query + " burak akgül")
    new_words = normalized_words(after)
    if not new_words <= allowed:
        raise ValueError("proposal introduces words not present in verified page content")
    query_words = normalized_words(candidate.query)
    if not query_words <= new_words:
        raise ValueError("proposal does not preserve the target-query meaning")


def gemini_proposal(con: sqlite3.Connection, candidate: Candidate) -> tuple[str, str, str]:
    values = env_values()
    key = values.get("GEMINI_API_KEY") or values.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("Gemini key is not configured; deterministic analysis completed without AI")
    before = current_meta(candidate.language)
    payload_text = json.dumps({
        "task": "Choose exactly one safe SEO metadata change for an existing page.",
        "rules": ["Return JSON only", "field must be title or description", "Do not add facts",
                  "Use only words already present in current metadata or target query", "No new page or URL"],
        "candidate": asdict(candidate), "current": before,
        "output_schema": {"field": "title|description", "value": "string", "reason": "short string"},
    }, ensure_ascii=False, sort_keys=True)
    prompt_hash = hashlib.sha256((MODEL + payload_text).encode()).hexdigest()
    cached = con.execute("SELECT response_json FROM seo_ai_cache WHERE prompt_hash=?", (prompt_hash,)).fetchone()
    if cached:
        raw = json.loads(cached[0])
    else:
        week = (dt.date.today() - dt.timedelta(days=7)).isoformat()
        used = con.execute("SELECT COUNT(*) FROM seo_ai_usage WHERE created_at>=?", (week,)).fetchone()[0]
        if used >= 1:
            raise RuntimeError("weekly SEO Gemini budget already used")
        body = json.dumps({"contents": [{"parts": [{"text": payload_text}]}],
                           "generationConfig": {"temperature": 0.15, "responseMimeType": "application/json"}}).encode()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={key}"
        result = None
        for attempt, delay in enumerate((0, 2, 5, 11)):
            if delay:
                time.sleep(delay)
            try:
                req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=90) as response:
                    result = json.loads(response.read())
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    con.execute("INSERT INTO seo_ai_usage(created_at,model,prompt_hash,result) VALUES(?,?,?,?)",
                                (dt.datetime.now(dt.timezone.utc).isoformat(), MODEL, prompt_hash, "quota_exhausted"))
                    con.commit()
                    raise RuntimeError("Gemini quota exhausted; no site change made") from None
                if exc.code not in (500, 502, 503, 504) or attempt == 3:
                    raise RuntimeError(f"Gemini HTTP {exc.code}; no site change made") from None
        if result is None:
            raise RuntimeError("Gemini retry budget exhausted")
        text = result["candidates"][0]["content"]["parts"][0]["text"]
        raw = json.loads(text)
        tokens = int((result.get("usageMetadata") or {}).get("promptTokenCount") or 0)
        con.execute("INSERT INTO seo_ai_cache VALUES(?,?,?,?)", (prompt_hash, MODEL, json.dumps(raw, ensure_ascii=False), dt.datetime.now(dt.timezone.utc).isoformat()))
        con.execute("INSERT INTO seo_ai_usage(created_at,model,prompt_hash,result,prompt_tokens) VALUES(?,?,?,?,?)",
                    (dt.datetime.now(dt.timezone.utc).isoformat(), MODEL, prompt_hash, "ok", tokens))
        con.commit()
    field, after = str(raw.get("field", "")), str(raw.get("value", "")).strip()
    validate_proposal(candidate, field, before.get(field, ""), after)
    return field, after, prompt_hash


def run(cmd: list[str], *, cwd: Path = REPO, check: bool = True) -> str:
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if check and result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip()[:500])
    return result.stdout.strip()


def validate_site() -> None:
    expected = set(DIST_BY_LANG.values())
    if not all((REPO / p).is_file() for p in expected):
        raise RuntimeError("required language page missing")
    if "cloud.umami.is/script.js" not in (REPO / "dist/app.js").read_text():
        raise RuntimeError("Umami loader missing")
    for lang, rel in DIST_BY_LANG.items():
        text = (REPO / rel).read_text()
        if len(re.findall(r"<title>.*?</title>", text, re.I | re.S)) != 1:
            raise RuntimeError(f"invalid title in {lang}")
        if len(re.findall(r'<meta\s+name="description"', text, re.I)) != 1:
            raise RuntimeError(f"invalid description in {lang}")
        url = "https://burakakgul.com" + ({"tr": "/", "en": "/en/", "de": "/de/"}[lang])
        if f'rel="canonical" href="{url}"' not in text:
            raise RuntimeError(f"canonical missing in {lang}")
        for code in ("tr", "en", "de", "x-default"):
            if f'hreflang="{code}"' not in text:
                raise RuntimeError(f"hreflang {code} missing in {lang}")
        for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, re.I | re.S):
            json.loads(html.unescape(block))


def validate_live(language: str, field: str, expected: str) -> None:
    page = {"tr": "/", "en": "/en/", "de": "/de/"}[language]
    last_error = "deployment not visible"
    for delay in (3, 6, 12, 24, 30):
        time.sleep(delay)
        try:
            with urllib.request.urlopen("https://burakakgul.com" + page, timeout=25) as response:
                document = response.read().decode("utf-8", "replace")
            with urllib.request.urlopen("https://burakakgul.com/app.js", timeout=25) as response:
                javascript = response.read().decode("utf-8", "replace")
            if field == "title":
                visible = html.escape(expected, quote=False) in document or expected in html.unescape(document)
            else:
                visible = html.escape(expected, quote=True) in document or expected in html.unescape(document)
            if not visible:
                last_error = f"deployed {field} is not visible"
                continue
            if "cloud.umami.is/script.js" not in javascript:
                last_error = "Umami loader missing from live app.js"
                continue
            return
        except (OSError, urllib.error.URLError) as exc:
            last_error = str(exc)
    raise RuntimeError(f"live validation failed: {last_error}")


def backup_repo() -> Path:
    BACKUPS.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = BACKUPS / f"site-before-seo-{stamp}.tar.gz"
    with tarfile.open(target, "w:gz") as tar:
        for name in ("build.py", "seo-overrides.json", "dist"):
            path = REPO / name
            if path.exists():
                tar.add(path, arcname=name)
    return target


def update_override(language: str, field: str, value: str) -> None:
    path = REPO / "seo-overrides.json"
    data = json.loads(path.read_text()) if path.is_file() else {}
    data.setdefault(language, {})[field] = value
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    run(["python3", "build.py"])


def deploy_change(con: sqlite3.Connection, candidate: Candidate, field: str, after: str, prompt_hash: str) -> str:
    dirty = run(["git", "status", "--porcelain"])
    if dirty:
        raise RuntimeError("site repository has uncommitted changes; safe auto-apply refused")
    recent = con.execute("SELECT COUNT(*) FROM seo_changes WHERE created_at>=? AND status IN ('deployed','pending_measurement')",
                         ((dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)).isoformat(),)).fetchone()[0]
    cool = con.execute("SELECT COUNT(*) FROM seo_changes WHERE page=? AND field=? AND created_at>=?",
                       (candidate.page, field, (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=COOLDOWN_DAYS)).isoformat())).fetchone()[0]
    if recent >= WEEKLY_LIMIT or cool:
        raise RuntimeError("weekly limit or field cooldown prevents a change")
    before = current_meta(candidate.language)[field]
    commit_before = run(["git", "rev-parse", "HEAD"])
    backup = backup_repo()
    saved = {p: (REPO / p).read_bytes() for p in ["seo-overrides.json", *DIST_BY_LANG.values()] if (REPO / p).exists()}
    try:
        update_override(candidate.language, field, after)
        validate_site()
        run(["git", "add", "seo-overrides.json", "dist"])
        run(["git", "commit", "-m", f"SEO: improve {field} for {candidate.query}"])
        commit_after = run(["git", "rev-parse", "HEAD"])
        run(["git", "push", "origin", "main"])
        try:
            validate_live(candidate.language, field, after)
        except Exception:
            run(["git", "revert", "--no-edit", commit_after])
            rollback_commit = run(["git", "rev-parse", "HEAD"])
            run(["git", "push", "origin", "main"])
            con.execute("""INSERT INTO seo_changes(created_at,query,page,language,field,old_value,new_value,
              baseline_json,confidence,model,prompt_hash,backup_path,commit_before,commit_after,deploy_url,status,
              evaluate_after,evaluated_at,outcome,rollback_commit,notes)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (dt.datetime.now(dt.timezone.utc).isoformat(), candidate.query, candidate.page, candidate.language,
               field, before, after, json.dumps(asdict(candidate), ensure_ascii=False, sort_keys=True),
               candidate.confidence, MODEL, prompt_hash, str(backup), commit_before, commit_after,
               "https://burakakgul.com" + candidate.page, "rolled_back",
               dt.date.today().isoformat(), dt.datetime.now(dt.timezone.utc).isoformat(), "deploy_validation_failed",
               rollback_commit, "automatic rollback after failed live validation"))
            con.commit()
            raise
    except Exception:
        for rel, content in saved.items():
            (REPO / rel).write_bytes(content)
        run(["git", "reset", "--mixed", "HEAD"], check=False)
        raise
    baseline = json.dumps(asdict(candidate), ensure_ascii=False, sort_keys=True)
    con.execute("""INSERT INTO seo_changes(created_at,query,page,language,field,old_value,new_value,
      baseline_json,confidence,model,prompt_hash,backup_path,commit_before,commit_after,deploy_url,status,evaluate_after)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
      (dt.datetime.now(dt.timezone.utc).isoformat(), candidate.query, candidate.page, candidate.language,
       field, before, after, baseline, candidate.confidence, MODEL, prompt_hash, str(backup), commit_before,
       commit_after, "https://burakakgul.com" + candidate.page, "pending_measurement",
       (dt.date.today() + dt.timedelta(days=14)).isoformat()))
    con.commit()
    return commit_after


def rollback_change(con: sqlite3.Connection, change: sqlite3.Row) -> str:
    if run(["git", "status", "--porcelain"]):
        raise RuntimeError("site repository is dirty; automatic rollback refused")
    backup_repo()
    update_override(change["language"], change["field"], change["old_value"])
    validate_site()
    run(["git", "add", "seo-overrides.json", "dist"])
    run(["git", "commit", "-m", f"SEO rollback: {change['field']} for {change['query']}"])
    rollback_commit = run(["git", "rev-parse", "HEAD"])
    run(["git", "push", "origin", "main"])
    validate_live(change["language"], change["field"], change["old_value"])
    con.execute("UPDATE seo_changes SET status='rolled_back',rollback_commit=?,notes=? WHERE id=?",
                (rollback_commit, "automatic rollback after material CTR and position regression", change["id"]))
    con.commit()
    return rollback_commit


def metric(con: sqlite3.Connection, query: str, page: str, start: dt.date, end: dt.date) -> dict[str, float]:
    row = con.execute("""SELECT SUM(clicks),SUM(impressions),
      SUM(position*impressions)/NULLIF(SUM(impressions),0) FROM search_performance
      WHERE query=? AND page LIKE ? AND day BETWEEN ? AND ?""",
      (query, "%" + page, start.isoformat(), end.isoformat())).fetchone()
    clicks, impressions, position = (float(x or 0) for x in row)
    return {"clicks": clicks, "impressions": impressions, "ctr": clicks / impressions if impressions else 0.0, "position": position}


def evaluate(con: sqlite3.Connection) -> list[str]:
    latest_raw = con.execute("SELECT MAX(day) FROM search_performance").fetchone()[0]
    if not latest_raw:
        return []
    latest = dt.date.fromisoformat(latest_raw)
    notes = []
    for change in con.execute("SELECT * FROM seo_changes WHERE status='pending_measurement' AND evaluate_after<=?", (latest.isoformat(),)).fetchall():
        deployed = dt.date.fromisoformat(change["created_at"][:10])
        before = metric(con, change["query"], change["page"], deployed - dt.timedelta(days=14), deployed - dt.timedelta(days=1))
        after = metric(con, change["query"], change["page"], latest - dt.timedelta(days=13), latest)
        if after["impressions"] < 60:
            notes.append(f"#{change['id']} ölçüm belirsiz; düşük trafik nedeniyle korunuyor")
            continue
        bad = after["ctr"] < before["ctr"] * .70 and after["position"] > before["position"] + 1.5
        outcome = "worse" if bad else "keep"
        con.execute("UPDATE seo_changes SET evaluated_at=?,outcome=?,status=? WHERE id=?",
                    (dt.datetime.now(dt.timezone.utc).isoformat(), outcome, "rollback_required" if bad else "measured", change["id"]))
        con.commit()
        if bad:
            try:
                commit = rollback_change(con, change)
                notes.append(f"#{change['id']} belirgin kötüleşti; otomatik rollback: {commit[:12]}")
            except Exception as exc:
                notes.append(f"#{change['id']} rollback gerekli ancak uygulanamadı: {exc}")
        else:
            notes.append(f"#{change['id']} ölçüm sonucu: {outcome}")
    con.commit()
    return notes


def send_telegram(message: str) -> None:
    values = env_values()
    token = values.get("TELEGRAM_BOT_TOKEN", "")
    ids = [x.strip() for x in values.get("TELEGRAM_CHAT_IDS", "").split(",") if x.strip()]
    if not token or not ids:
        return
    for chat_id in ids:
        body = json.dumps({"chat_id": chat_id, "text": message, "disable_web_page_preview": True}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30):
            pass


def format_candidate(c: Candidate) -> str:
    return (f"Sorgu: {c.query}\nPozisyon: {c.position:.1f} · Gösterim: {c.impressions:.0f} · "
            f"CTR: %{c.ctr*100:.1f} · Beklenen: %{c.expected_ctr*100:.1f}\nGüven: {c.confidence:.2f}")


def doctor(con: sqlite3.Connection) -> int:
    latest = con.execute("SELECT MAX(day) FROM search_performance").fetchone()[0]
    values = env_values()
    print(f"Database: {'ready' if DB.is_file() else 'missing'} ({DB})")
    print(f"Latest GSC data: {latest or 'none'}")
    print(f"Site repository: {'ready' if (REPO / '.git').is_dir() else 'missing'} ({REPO})")
    print(f"Git branch: {run(['git','branch','--show-current'], check=False) or 'unknown'}")
    print(f"Gemini key: {'set' if values.get('GEMINI_API_KEY') or values.get('GOOGLE_API_KEY') else 'missing (safe no-op)'}")
    print(f"Gemini model: {MODEL}; weekly generate budget: 1")
    print(f"Thresholds: impressions>={MIN_IMPRESSIONS}, active_days>={MIN_DAYS}, confidence>={MIN_CONFIDENCE}, cooldown={COOLDOWN_DAYS}d")
    try:
        validate_site()
        print("Site safety checks: pass (3 languages, canonical/hreflang/schema/Umami)")
    except Exception as exc:
        print(f"Site safety checks: FAIL ({exc})")
        return 2
    return 0


def weekly(con: sqlite3.Connection, dry_run: bool, send: bool) -> int:
    measured = evaluate(con)
    found = candidates(con)
    if not found:
        latest = con.execute("SELECT MAX(day) FROM search_performance").fetchone()[0]
        msg = ("📈 burakakgul.com — Otomatik SEO\n"
               f"Son GSC verisi: {latest or 'yok'}\n"
               f"Bu hafta veri yetersiz / değişiklik yok. Eşik: sorgu başına ≥{MIN_IMPRESSIONS} gösterim, "
               f"≥{MIN_DAYS} aktif gün ve ≥{MIN_CONFIDENCE:.2f} güven.\nRollback: gerekmedi.")
        if measured:
            msg += "\n" + "\n".join(measured)
        print(msg)
        if send and not dry_run:
            send_telegram(msg)
        return 0
    c = found[0]
    if dry_run:
        msg = "DRY RUN — değişiklik uygulanmadı\n" + format_candidate(c) + "\nEn fazla 1 değişiklik değerlendirilecek."
        print(msg)
        return 0
    try:
        field, after, prompt_hash = gemini_proposal(con, c)
        before = current_meta(c.language)[field]
        commit = deploy_change(con, c, field, after, prompt_hash)
        msg = ("✅ burakakgul.com — kontrollü SEO değişikliği\n" + format_candidate(c) +
               f"\nAlan/dosya: {field} · {DIST_BY_LANG[c.language]}\nÖnce: {before}\nSonra: {after}"
               f"\nRelease/commit: {commit[:12]}\nRollback: otomatik yedek + önceki commit kayıtlı; ilk ölçüm ≥14 gün sonra.")
    except Exception as exc:
        msg = "ℹ️ burakakgul.com — değişiklik yok\n" + format_candidate(c) + f"\nNeden: {exc}\nProduction korunuyor."
    print(msg)
    if send:
        send_telegram(msg)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Controlled weekly SEO automation")
    parser.add_argument("command", choices=("doctor", "dry-run", "weekly"))
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()
    con = connect()
    try:
        return doctor(con) if args.command == "doctor" else weekly(con, args.command == "dry-run", args.send)
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
