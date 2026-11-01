"""QA-01: 从实际测试 ID 重新生成 104 矩阵证据。"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def collect_test_ids() -> dict[str, list[str]]:
    """从测试文件收集实际存在的 test 函数名。"""
    test_ids: dict[str, list[str]] = {}
    for p in (ROOT / "tests" / "unit").glob("test_*.py"):
        src = p.read_text(encoding="utf-8", errors="replace")
        funcs = re.findall(r"def (test_\w+)", src)
        test_ids[p.name] = funcs
    return test_ids


def main() -> None:
    matrix_path = ROOT / "docs" / "ACCEPTANCE_104_MATRIX.json"
    if not matrix_path.exists():
        print("matrix not found")
        return
    cases = json.loads(matrix_path.read_text(encoding="utf-8"))
    test_ids = collect_test_ids()

    fixed = 0
    for c in cases:
        ev = c.get("evidence") or ""
        # 检查 evidence 中的 file.py::test_name 是否存在
        m = re.findall(r"(\w+\.py)::(test_\w+)", ev)
        for fname, tname in m:
            if fname in test_ids:
                if tname in test_ids[fname]:
                    continue  # 真实存在
                # 找相近的
                close = [t for t in test_ids[fname] if tname[:15] in t or t[:15] in tname]
                if close:
                    c["evidence"] = ev.replace(f"{fname}::{tname}", f"{fname}::{close[0]}")
                    c["notes"] = f"fixed test ref: {tname} -> {close[0]}"
                    fixed += 1
                else:
                    c["status"] = "NOT_TESTED"
                    c["evidence"] = ""
                    c["notes"] = f"test {fname}::{tname} not found"
                    fixed += 1
            else:
                c["status"] = "NOT_TESTED"
                c["evidence"] = ""
                c["notes"] = f"file {fname} not found"
                fixed += 1

    matrix_path.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"fixed {fixed} evidence refs")

    # 重新生成 markdown
    from collections import Counter

    lines = [
        "# FlightHunter 104 项验收矩阵",
        "",
        "**口径：** PASS 需证据；NOT_TESTED 诚实标注；禁止假绿。",
        f"**条数：** {len(cases)}",
        "",
        "| ID | 类别 | 用例 | 方法 | 状态 | 证据 |",
        "|---|---|---|---|---|---|",
    ]
    for c in cases:
        lines.append(
            f"| {c['id']} | {c['category']} | {c['title']} | {c['method']} | {c['status']} | {c.get('evidence') or '—'} |"
        )
    cnt = Counter(c["status"] for c in cases)
    lines += ["", "## 汇总", ""]
    for k, v in sorted(cnt.items()):
        lines.append(f"- **{k}**: {v}")
    (ROOT / "docs" / "ACCEPTANCE_104_MATRIX.md").write_text("\n".join(lines), encoding="utf-8")
    print(cnt)


if __name__ == "__main__":
    main()
