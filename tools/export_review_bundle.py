#!/usr/bin/env python3
"""Make a self-contained, commit-pinned ChatGPT review ZIP from a local Git repo.

Uses only Python's standard library and Git; pytest and Ruff are optional external commands.
Does not upload files or call an AI API.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

SENSITIVE_RE = re.compile(
    r"(^|/)(?:\.env(?:\.[^/]*)?|auth\.json|credentials\.json|"
    r"service[_-]?account\.json|secrets?(?:/|\.)|data/|"
    r"id_(?:rsa|ed25519)(?:\.pub)?|[^/]+\.(?:pem|p12|pfx|key))$",
    re.IGNORECASE,
)
MAX_TRACKED_FILE = 12 * 1024 * 1024
MAX_SOURCE_TOTAL = 45 * 1024 * 1024


def run(args: list[str], cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=cwd, text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
        shell=False,
    )


def git(root: Path, *args: str) -> str:
    result = run(["git", *args], root)
    if result.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stdout[:2000]}")
    return result.stdout.strip()


def _norm_path(p: str) -> str:
    return p.replace("\\", "/").rstrip("/").lower()


def ruff_argv() -> list[str]:
    """优先 venv 内 ruff；否则 uv run ruff；最后 PATH 中的 ruff。"""
    import shutil

    venv_ruff = Path(sys.executable).parent / ("ruff.exe" if os.name == "nt" else "ruff")
    if venv_ruff.is_file():
        return [str(venv_ruff), "check", "."]
    mod = run([sys.executable, "-m", "ruff", "--version"], Path.cwd(), 15)
    if mod.returncode == 0:
        return [sys.executable, "-m", "ruff", "check", "."]
    uv = shutil.which("uv")
    if uv:
        return [uv, "run", "ruff", "check", "."]
    which = shutil.which("ruff")
    if which:
        return [which, "check", "."]
    return ["ruff", "check", "."]


def check_sensitive(path: str) -> bool:
    if path in {".env.example", ".env.sample", ".env.template"}:
        return False
    parts = [part.lower() for part in PurePosixPath(path).parts]
    if ".git" in parts or "data" in parts or "secrets" in parts or ".secrets" in parts:
        return True
    return bool(SENSITIVE_RE.search(path))


def get_source(root: Path) -> list[tuple[str, bytes]]:
    p = subprocess.run(["git", "archive", "--format=zip", "HEAD"], cwd=root,
                       capture_output=True, timeout=120)
    if p.returncode:
        raise RuntimeError("无法从 HEAD 导出源码：" + p.stderr.decode("utf-8", "replace")[:1000])
    items: list[tuple[str, bytes]] = []
    total = 0
    with zipfile.ZipFile(io.BytesIO(p.stdout)) as source_zip:
        for name in source_zip.namelist():
            if name.endswith("/"):
                continue
            safe = PurePosixPath(name)
            if safe.is_absolute() or ".." in safe.parts:
                raise RuntimeError("异常 Git 路径：" + name)
            if check_sensitive(name):
                raise RuntimeError(
                    f"检测到敏感文件名仍被 Git 跟踪：{name}\n"
                    "请先确认文件是否含密钥/个人数据，清理后再导出。"
                )
            info = source_zip.getinfo(name)
            if info.file_size > MAX_TRACKED_FILE:
                raise RuntimeError(f"单文件过大，请人工检查后再打包：{name}")
            total += info.file_size
            if total > MAX_SOURCE_TOTAL:
                raise RuntimeError("仓库源码总大小超过45MiB，停止导出以避免生成无法审核的大包。")
            items.append(("source/" + name, source_zip.read(info)))
    return items


def check_command(args: list[str], cwd: Path, timeout: int) -> dict:
    try:
        t0 = time.monotonic()
        result = run(args, cwd, timeout)
        return {"command": args, "exit_code": result.returncode,
                "elapsed_seconds": round(time.monotonic()-t0, 2),
                "output": result.stdout[-140000:]}
    except FileNotFoundError as exc:
        return {"command": args, "exit_code": None, "elapsed_seconds": 0,
                "output": f"NOT EXECUTED: {exc}"}
    except subprocess.TimeoutExpired:
        return {"command": args, "exit_code": None, "elapsed_seconds": timeout,
                "output": "TIMEOUT: 测试未完成，不能报告通过"}


def main() -> int:
    ap = argparse.ArgumentParser(description="生成 ChatGPT 可独立审核的源码包（不上传）")
    ap.add_argument("--repo", default=".", help="Git 仓库目录（默认当前目录）")
    ap.add_argument("--base", help="增量审核起点 SHA，例如 805ed36")
    ap.add_argument("--skip-tests", action="store_true", help="不执行 pytest/Ruff；清晰标明未测试")
    ap.add_argument("--out-dir", default="review_exports")
    opts = ap.parse_args()
    try:
        root = Path(opts.repo).resolve()
        toplevel = git(root, "rev-parse", "--show-toplevel")
        if _norm_path(toplevel) != _norm_path(root.as_posix()):
            raise RuntimeError(
                f"请在仓库根目录运行，或者用 --repo 指定仓库根目录\n"
                f"  root={root}\n  toplevel={toplevel}"
            )
        dirty = git(root, "status", "--porcelain", "--untracked-files=no")
        if dirty:
            raise RuntimeError("存在尚未提交的已跟踪文件；请先提交后再导出，保证测试与 SHA 对应：\n" + dirty[:1000])
        head = git(root, "rev-parse", "HEAD")
        output_dir = root / opts.out_dir
        statefile = output_dir / "last_exported_sha.txt"
        base = opts.base or (statefile.read_text(encoding="utf-8").strip() if statefile.exists() else None)
        if base == head and not opts.base:
            # An accidental second export of the same SHA must not erase the diff.
            base = None
        if not base:
            previous = run(["git", "rev-parse", "HEAD~1"], root)
            base = previous.stdout.strip() if previous.returncode == 0 else None
        if base:
            base = git(root, "rev-parse", base)
            if base == head:
                print("提示：起点与当前 HEAD 相同，Diff 为空；仍会导出完整源码。")
        source = get_source(root)
        diff = git(root, "diff", "--no-ext-diff", "--find-renames", f"{base}..{head}") if base else "BASE NOT AVAILABLE"
        changelist = git(root, "diff", "--name-status", f"{base}..{head}") if base else "BASE NOT AVAILABLE"
        log = git(root, "log", "--date=iso-strict", "--pretty=format:%h %ad %s", "-n", "20")
        result_pytest = None if opts.skip_tests else check_command(
            [sys.executable, "-m", "pytest", "-q"], root, 300
        )
        result_ruff = None if opts.skip_tests else check_command(ruff_argv(), root, 90)
        manifest = {
            "project": root.name,
            "source_origin": "git archive HEAD; complete tracked-source snapshot",
            "head_sha": head, "base_sha": base,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "tests": {
                "pytest": "not_run" if result_pytest is None else result_pytest["exit_code"],
                "ruff": "not_run" if result_ruff is None else result_ruff["exit_code"],
            },
            "notes": [
                "本包只对应 head_sha，不代表 GitHub 远端已经有此提交；需要提交推送记录另行确认。",
                "测试运行于当前干净工作树；依赖环境是否完整仍须看原始日志。",
                "源码、diff 和日志可能携带敏感信息，上传前请人工检查；文件名拦截并非安全保证。",
                "不自动判断需求 done/partial；需独立审查。",
            ],
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / f"FlightHunter-review-{head[:8]}.zip"
        readme = (
            "# FlightHunter 代码审核包\n\n"
            f"目标提交：`{head}`\n基准提交：`{base or '无'}`\n\n"
            "请先完整阅读 `source/docs/REVIEW_FOR_GPT.md`，随后核对 `reports/changes.diff`、实际源码和测试日志。"
            "不得把未执行测试、Mock 或 partial 认定为 done。请按该文档要求输出中文审核结果。\n\n"
            "- `source/`: HEAD 完整跟踪源码\n"
            "- `reports/changes.diff`: 从基准到 HEAD 的增量差异\n"
            "- `reports/changed_files.txt`: 修改文件列表\n"
            "- `reports/pytest.txt` / `reports/ruff.txt`: 原始测试日志\n"
            "- `reports/commits.txt`: 最近提交\n"
            "- `manifest.json`: SHA、测试退出码和创建日期\n"
        )
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for name, content in source:
                z.writestr(name, content)
            z.writestr("README_REVIEW.md", readme)
            z.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            z.writestr("reports/changes.diff", diff)
            z.writestr("reports/changed_files.txt", changelist)
            z.writestr("reports/commits.txt", log)
            for label, result in [("pytest", result_pytest), ("ruff", result_ruff)]:
                z.writestr(f"reports/{label}.txt", (
                    "NOT RUN --skip-tests\n" if result is None else
                    f"Command: {' '.join(result['command'])}\nExit code: {result['exit_code']}\nElapsed: {result['elapsed_seconds']}s\n\n{result['output']}"
                ))
        statefile.write_text(head + "\n", encoding="utf-8")
        print("审核包已生成：", target)
        print("HEAD：", head)
        print("BASE：", base or "无")
        print("测试状态：", manifest["tests"])
        print("请检查 ZIP 不包含隐私或密钥，再上传到 ChatGPT；未自动上传。")
        return 0
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as e:
        print("ERROR:", e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
