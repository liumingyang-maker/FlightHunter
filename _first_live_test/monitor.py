"""Local read-only regression watcher for FlightHunter first live test.
No AI calls; sends no data anywhere. Writes redacted, machine-readable alerts.jsonl.
"""
from __future__ import annotations
import argparse
import json
import re
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SECRET_PATTERNS = [
    (re.compile(r"(?i)(bearer\s+)[a-z0-9_+./=-]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)((?:api[_-]?token|password|secret|access[_-]?token|cookie|authorization)\s*[:=]\s*)[^\s&]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)([?&](?:key|token|code|access_token|api_key|session|auth)=)[^&\s]+"), r"\1[REDACTED]"),
    (re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"), "[EMAIL_REDACTED]"),
]

def scrub(text: str) -> str:
    for pattern, repl in SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text[:700]


def connect_readonly(p: Path):
    return sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)


def counts(db: Path) -> dict:
    if not db.exists():
        return {"db_missing": True}
    try:
        with connect_readonly(db) as con:
            con.row_factory = sqlite3.Row
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            def q(sql: str, table: str) -> int:
                if table not in tables:
                    return 0
                return int(con.execute(sql).fetchone()[0])
            result = {
                "sources": q("SELECT count(*) FROM sources", "sources"),
                "sources_fetched": q("SELECT count(*) FROM sources WHERE last_fetch_at IS NOT NULL", "sources"),
                "raw_candidates": q("SELECT count(*) FROM raw_candidates", "raw_candidates"),
                "raffle_real": q("SELECT count(*) FROM campaign_rounds WHERE demo_only=0", "campaign_rounds"),
                "raffle_verified": q("SELECT count(*) FROM campaign_rounds WHERE demo_only=0 AND verify_status='verified'", "campaign_rounds"),
                "benefits_real": q("SELECT count(*) FROM benefit_offers WHERE demo_only=0", "benefit_offers"),
                "benefits_confirmed": q("SELECT count(*) FROM benefit_offers WHERE demo_only=0 AND date_certainty='confirmed_for_dates'", "benefit_offers"),
                "fare_signals": q("SELECT count(*) FROM fare_deal_signals", "fare_deal_signals"),
                "evidence_aggregator": q("SELECT count(*) FROM evidences WHERE field_path='aggregator_page_snapshot'", "evidences"),
                "evidence_official": q("SELECT count(*) FROM evidences WHERE field_path='official_page_snapshot'", "evidences"),
                "task_failures": q("SELECT count(*) FROM task_runs WHERE status IN ('blocked','failed','partial') AND dry_run=0", "task_runs"),
            }
            issues = {}
            if "campaign_rounds" in tables:
                issues["VERIFIED_NO_URL"] = q("SELECT count(*) FROM campaign_rounds WHERE demo_only=0 AND verify_status='verified' AND (official_url IS NULL OR official_url='')", "campaign_rounds")
            if "evidences" in tables:
                issues["REPEATED_SAME_SNAPSHOT"] = q("SELECT count(*) FROM (SELECT entity_id,source_url,content_hash,field_path, count(*) n FROM evidences WHERE field_path='aggregator_page_snapshot' GROUP BY 1,2,3,4 HAVING n>1)", "evidences")
            result["alerts"] = issues
            return result
    except Exception as exc:
        return {"db_error": scrub(str(exc))}


class Watcher:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.logdir = run_dir / "logs"
        self.issues = run_dir / "alerts.jsonl"
        self.metrics = run_dir / "metrics.jsonl"
        self.db = run_dir / "snapshot" / "data" / "flighthunter-live-test.db"
        self.offsets = defaultdict(int)
        self.seen = set()
        self.last_counts = {}
        self.have_sweep_end = False
        self.start_time = time.monotonic()
        self.logdir.mkdir(parents=True, exist_ok=True)
        if self.issues.exists():
            for line in self.issues.read_text(encoding="utf-8", errors="replace").splitlines():
                try: self.seen.add(json.loads(line)["fingerprint"])
                except Exception: pass

    def emit(self, severity: str, rule: str, message: str, *, discriminator: str = ""):
        fid = f"{rule}:{discriminator}"
        if fid in self.seen:
            return
        self.seen.add(fid)
        entry = {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "severity": severity, "rule": rule, "fingerprint": fid,
                 "message": scrub(message)}
        with self.issues.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"[{severity}] {rule}: {entry['message']}", flush=True)

    def tail_logs(self):
        for p in sorted(self.logdir.glob("*.log")):
            with p.open("rb") as f:
                f.seek(self.offsets[str(p)])
                data = f.read(131072)
                self.offsets[str(p)] = f.tell()
            if not data:
                continue
            for line in data.decode("utf-8", errors="replace").splitlines():
                t = line.strip()
                if not t:
                    continue
                lowered = t.lower()
                if "=== sweep complete ===" in lowered:
                    self.have_sweep_end = True
                if "integrityerror" in lowered or "no such column" in lowered or "operationalerror" in lowered or "database is locked" in lowered:
                    self.emit("P0", "DATABASE_EXCEPTION", f"{p.name}: {t}", discriminator=t[:120])
                elif "traceback (most recent call last)" in lowered:
                    self.emit("P1", "UNHANDLED_EXCEPTION", f"{p.name}: {t}", discriminator=p.name + t)
                elif re.search(r"(?:http\s+|status\s*code\s*[:=]\s*)(?:429|403)\b", lowered) or "robots.txt 不允许抓取" in t:
                    self.emit("WARN", "SOURCE_DENIED_OR_THROTTLED", f"{p.name}: {t}", discriminator=t[:120])
                elif re.search(r"=== result (\S+) exit=(\d+) ===", lowered):
                    m = re.search(r"=== result (\S+) exit=(\d+) ===", lowered)
                    if m and m.group(2) != "0":
                        self.emit("P1", "COMMAND_FAILED", f"{m.group(1)} exit={m.group(2)}", discriminator=m.group(1))
                elif "== source status: ok with 0 parsed" in lowered:
                    self.emit("WARN", "EMPTY_PARSE", t)

    def snapshot(self):
        c = counts(self.db)
        with self.metrics.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"utc": datetime.now(timezone.utc).isoformat(), **c}, ensure_ascii=False) + "\n")
        if "db_error" in c:
            self.emit("P0", "DATABASE_READ_FAILURE", c["db_error"], discriminator=c["db_error"][:100])
        if c.get("alerts",{}).get("VERIFIED_NO_URL"):
            self.emit("P0", "VERIFIED_WITHOUT_OFFICIAL_URL", f"{c['alerts']['VERIFIED_NO_URL']} real rounds are verified without official URL")
        if c.get("alerts",{}).get("REPEATED_SAME_SNAPSHOT"):
            self.emit("P1", "REPEATED_AGGREGATOR_EVIDENCE", f"{c['alerts']['REPEATED_SAME_SNAPSHOT']} duplicated source/hash snapshots")
        if c.get("task_failures", 0) and c.get("task_failures",0) > self.last_counts.get("task_failures", 0):
            self.emit("WARN", "EXECUTION_PARTIAL_OR_BLOCKED", f"{c['task_failures']} failed/partial/blocked real task runs", discriminator=str(c['task_failures']))
        self.last_counts = c
        print("[METRICS] " + json.dumps({k:v for k,v in c.items() if k!="alerts"},ensure_ascii=False), flush=True)
        if self.have_sweep_end and not (c.get("raffle_real",0) or c.get("benefits_real",0) or c.get("fare_signals",0)):
            self.emit("WARN", "ZERO_BUSINESS_OUTPUT", "Live source requests ended; no new real raffle/benefit/fare records. Check robots, HTTP and parser before marking success")
        return c

    def loop(self, seconds: float = 3.0, once: bool = False):
        print(f"[WATCH] Local watcher started. run_dir={self.run_dir}; read-only DB; no API calls", flush=True)
        self.tail_logs()
        self.snapshot()
        if once:
            return
        try:
            while True:
                time.sleep(seconds)
                self.tail_logs()
                self.snapshot()
        except KeyboardInterrupt:
            print("[WATCH] stopped; local logs retained", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    Watcher(args.run_dir.resolve()).loop(args.interval, args.once)

if __name__ == "__main__":
    main()
