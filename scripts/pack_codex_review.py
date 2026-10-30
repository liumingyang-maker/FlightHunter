"""打包 Codex/GPT 复验 zip：源码快照 + 交接文档 + README。不含私人数据。"""

from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEAD = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
OUT = ROOT.parent / f"FlightHunter_CodeReview_{HEAD[:7]}.zip"

DOCS = [
    "docs/CODEX_SPRINT_CLOSEOUT_HANDOFF.md",
    "docs/SPRINT_CLOSEOUT_PLAN.md",
    "docs/REQUIREMENTS_MATRIX.md",
    "docs/TECH_DEBT.md",
    "docs/NOTIFY_DELIVERY_SEMANTICS.md",
    "docs/DAILY_RUNTIME_RUNBOOK.md",
    "docs/CODEX_BATCH_ACCEPTANCE.md",
    "docs/CODEX_IMPLEMENTATION_AUDIT_20261030.md",
    "docs/CODEX_PROJECT_GUIDE.md",
    "docs/PRODUCT_BASELINE_20261030.md",
    "CODEX_INDEPENDENT_AUDIT.md",
    "CODEX_AUDIT_MATRIX.json",
]

README = f"""# FlightHunter 复验包

- HEAD: `{HEAD}`
- 分支: develop（已 push GitHub）
- 用途: 交 Codex / GPT 独立复验

## 建议先读
1. `docs/CODEX_SPRINT_CLOSEOUT_HANDOFF.md` — 任务书（含三问与负例）
2. `docs/REQUIREMENTS_MATRIX.md` — 诚实矩阵
3. `docs/SPRINT_CLOSEOUT_PLAN.md` — 冲刺计划
4. `docs/TECH_DEBT.md` — 遗留风险

## 复验命令（勿碰正式库）
```powershell
$env:PYTHONPATH='.'; .\\.venv\\Scripts\\python.exe -B -m pytest tests/unit -q -p no:cacheprovider
.\\.venv\\Scripts\\python.exe -B scripts/label_samples.py
.\\.venv\\Scripts\\python.exe -B scripts/selfcheck_r_series.py
.\\.venv\\Scripts\\python.exe -B scripts/smoke_after_codex_merge.py
.\\.venv\\Scripts\\python.exe -B scripts/isolated_migrate_drill.py
```

## 不含
- data/ 正式库、auth.json、Cookies、.venv、运行日志
- 实时报价 API、自动购票/报名

**iMiMo 不自签关单；以独立复验结论为准。**
"""


def main() -> None:
    # 1) git archive 源码（不含 data/.venv 等）
    tarball = ROOT.parent / f"fh_src_{HEAD[:7]}.tar"
    subprocess.check_call(
        ["git", "archive", "--format=tar", "-o", str(tarball), HEAD],
        cwd=ROOT,
    )
    # 2) zip 组装
    if OUT.exists():
        OUT.unlink()
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README_CODEX_REVIEW.md", README)
        seen: set[str] = set()
        import tarfile

        with tarfile.open(tarball) as tf:
            for m in tf.getmembers():
                if not m.isfile():
                    continue
                name = m.name.replace("\\", "/")
                if any(
                    name.startswith(p)
                    for p in (
                        "data/",
                        ".venv/",
                        "auth.json",
                        ".git/",
                    )
                ):
                    continue
                f = tf.extractfile(m)
                if f is None:
                    continue
                seen.add(name)
                zf.writestr(f"FlightHunter/{name}", f.read())
        for d in DOCS:
            p = ROOT / d
            if p.exists() and d not in seen:
                zf.write(p, f"FlightHunter/{d}")
    tarball.unlink(missing_ok=True)
    size = OUT.stat().st_size
    print(f"OUT={OUT}")
    print(f"SIZE_MB={size/1024/1024:.2f}")
    print(f"HEAD={HEAD}")


if __name__ == "__main__":
    main()
