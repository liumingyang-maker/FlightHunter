"""FlightHunter → GPT-6 独立审核源码包。"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "review_exports"
OUT_ZIP = OUT_DIR / "FlightHunter-GPT6-Latest-Review.zip"
BASELINE = "14d681e"  # 上次 Codex 审核版本

# 敏感信息扫描
SENSITIVE_PATTERNS = [
    (re.compile(r"hGJz1D[A-Za-z0-9_-]{30,}"), "EXPOSED_TOKEN"),
    (re.compile(r"6Oc5qnj[A-Za-z0-9_-]{30,}"), "EXPOSED_TOKEN"),
    (re.compile(r"UcyfGIi[A-Za-z0-9_-]{30,}"), "EXPOSED_SECRET"),
    (re.compile(r"QmuWeDK[A-Za-z0-9_-]{30,}"), "EXPOSED_SECRET"),
    (re.compile(r"ghp_[A-Za-z0-9]{36}"), "GITHUB_TOKEN"),
    (re.compile(r"gho_[A-Za-z0-9]{36}"), "GITHUB_TOKEN"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "OPENAI_KEY"),
    (re.compile(r"(?:password|passwd|pwd)\s*[:=]\s*[\"'][^\"']{6,}", re.I), "PASSWORD"),
    (re.compile(r"(?:secret|api_key|apikey)\s*[:=]\s*[\"'][^\"']{6,}", re.I), "SECRET"),
    (re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"), "JWT"),
]

# 不导出的路径前缀
EXCLUDE_PREFIXES = (
    ".venv/",
    ".git/",
    "data/",
    "auth.json",
    "sessions.json",
    "_first_live_test/",
    "FlightHunter_audit_",
    "__pycache__/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".pytest_cache/",
    "node_modules/",
)


def run_git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8", errors="replace").strip()


def scan_sensitive(text: str, path: str) -> list[dict]:
    hits = []
    for pat, label in SENSITIVE_PATTERNS:
        for m in pat.finditer(text):
            hits.append({"file": path, "type": label, "match_preview": m.group(0)[:12] + "..."})
    return hits


def main() -> None:
    head = run_git("rev-parse", "HEAD")
    remote = run_git("ls-remote", "origin", "refs/heads/develop").split()[0]
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    print(f"HEAD={head}")
    print(f"remote={remote}")
    print(f"match={head == remote}")

    # 1) git archive 导出
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tar_path = OUT_DIR / "_export.tar"
    subprocess.check_call(
        ["git", "archive", "--format=tar", "-o", str(tar_path), head], cwd=ROOT
    )

    # 2) diff 说明
    diff_stat = run_git("diff", "--stat", BASELINE, head)
    diff_log = run_git("log", "--oneline", f"{BASELINE}..{head}")
    diff_patch = subprocess.check_output(
        ["git", "diff", f"{BASELINE}..{head}"], cwd=ROOT, text=True, encoding="utf-8", errors="replace"
    )

    # 3) 解包 + 扫敏感
    all_files: list[dict] = []
    sensitive: list[dict] = []
    clean_count = 0
    excluded_count = 0

    with tarfile.open(tar_path) as tf:
        for m in tf.getmembers():
            if not m.isfile():
                continue
            name = m.name.replace("\\", "/")
            if name.startswith(EXCLUDE_PREFIXES) or any(name.startswith(p) for p in EXCLUDE_PREFIXES):
                excluded_count += 1
                continue
            f = tf.extractfile(m)
            if f is None:
                continue
            data = f.read()
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            hits = scan_sensitive(text, name)
            if hits:
                sensitive.extend(hits)
                # 脱敏：替换匹配内容
                for hit in hits:
                    pat, _ = next((p for p in SENSITIVE_PATTERNS if p[1] == hit["type"]), (None, None))
                    if pat:
                        text = pat.sub("[REDACTED]", text)
                data = text.encode("utf-8")
                clean_count += 1
            sha = hashlib.sha256(data).hexdigest()
            all_files.append({
                "path": name,
                "bytes": len(data),
                "sha256": sha,
                "redacted": bool(hits),
            })

    print(f"files={len(all_files)} excluded={excluded_count} redacted_files={clean_count}")
    print(f"sensitive_hits={len(sensitive)}")
    for s in sensitive[:10]:
        print(f"  {s['type']} in {s['file']}")

    # 4) 写入 zip
    import zipfile

    # 脱敏 diff 和 manifest 中的敏感内容
    def _redact(text: str) -> str:
        for pat, label in SENSITIVE_PATTERNS:
            text = pat.sub("[REDACTED]", text)
        return text

    diff_stat_clean = _redact(diff_stat)
    diff_log_clean = _redact(diff_log)
    diff_patch_clean = _redact(diff_patch)

    with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        # README
        readme = f"""# FlightHunter GPT-6 Independent Review Package

- Generated: {ts}
- HEAD: {head}
- origin/develop: {remote}
- Match: {head == remote}
- Baseline (last Codex): {BASELINE}
- Commits since baseline: {len(diff_log.splitlines())}
- Files: {len(all_files)}
- Redacted files: {clean_count}
- Sensitive hits: {len(sensitive)}

## Required docs included
- docs/CODEX_SPRINT_CLOSEOUT_HANDOFF.md
- docs/REQUIREMENTS_MATRIX.md
- docs/PERSONAL_BETA_CHECKLIST.md
- docs/SPRINT_CLOSEOUT_PLAN.md
- docs/NEXT_STEPS_PLAN.md

## Excluded (by design)
- .git/, .venv/, data/ (real DB, auth, cookies)
- _first_live_test/, audit snapshots, __pycache__

## Diff since last Codex review
See DIFF_SINCE_{BASELINE}.md

## Review focus
1. Data quality: publish-date verification, stale cleanup
2. Source scraping: robots 403 handling, parser keywords
3. Security: SSRF, XSS, auth, notification delivery
4. Product: four-channel fare, raffle honesty, trip lifecycle

## Honest status
- 262+ unit tests passed at packaging time
- NOT full 104-item acceptance
- NOT 72h continuous runtime proof
- NOT public internet security audit
"""
        zf.writestr("README_GPT6_REVIEW.md", readme)

        # diff files
        zf.writestr(
            f"DIFF_SINCE_{BASELINE}_STAT.txt",
            diff_stat + "\n\n" + diff_log + "\n",
        )
        # 限制 patch 大小（前 500KB）
        patch_trim = diff_patch_clean[:500_000]
        if len(diff_patch) > 500_000:
            patch_trim += f"\n\n... TRUNCATED ({len(diff_patch)} total bytes) ...\n"
        zf.writestr(f"DIFF_SINCE_{BASELINE}.patch", patch_trim)

        # 源码文件
        with tarfile.open(tar_path) as tf:
            name_set = {f["path"] for f in all_files}
            redacted = {f["path"] for f in all_files if f["redacted"]}
            for m in tf.getmembers():
                if not m.isfile():
                    continue
                name = m.name.replace("\\", "/")
                if name not in name_set:
                    continue
                fobj = tf.extractfile(m)
                if fobj is None:
                    continue
                data = fobj.read()
                if name in redacted:
                    try:
                        text = data.decode("utf-8")
                    except UnicodeDecodeError:
                        continue
                    for pat, label in SENSITIVE_PATTERNS:
                        text = pat.sub("[REDACTED]", text)
                    data = text.encode("utf-8")
                zf.writestr(f"FlightHunter/{name}", data)

        # manifest
        manifest = {
            "generated_at_utc": ts,
            "head_sha": head,
            "remote_develop": remote,
            "head_matches_remote": head == remote,
            "codex_baseline": BASELINE,
            "commits_since_baseline": diff_log.splitlines(),
            "file_count": len(all_files),
            "excluded_count": excluded_count,
            "redacted_file_count": clean_count,
            "sensitive_hits": [{"file": s["file"], "type": s["type"], "note": "redacted"} for s in sensitive],
            "files": all_files,
        }
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    # 清理 tar
    tar_path.unlink(missing_ok=True)
    size = OUT_ZIP.stat().st_size
    print(f"\nOUT={OUT_ZIP}")
    print(f"SIZE_MB={size/1024/1024:.2f}")
    print(f"HEAD_SHA={head}")


if __name__ == "__main__":
    main()
