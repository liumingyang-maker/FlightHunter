"""Playwright 执行器：打开页面、按预填计划填表、读取回执。

未安装 Playwright 浏览器时返回 blocked，不伪造成功。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.core.url_safety import assert_public_http_url
from app.models import CampaignRound, Profile
from app.services.browser.prefill import PrefillPlan, build_prefill_plan


@dataclass
class BrowserResult:
    ok: bool
    mode: str
    receipt_code: str | None = None
    status: str = "unknown"
    message: str = ""
    warnings: list[str] = field(default_factory=list)
    requires_human: list[str] = field(default_factory=list)


def _playwright_available() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


def fill_form_with_playwright(
    plan: PrefillPlan,
    *,
    file_url: str | None = None,
    submit: bool = False,
) -> BrowserResult:
    """对 file:// 模拟站或 http(s) 目标执行预填。默认不自动提交。"""
    target = file_url or plan.target_url
    if target.startswith("file:"):
        # 本地模拟站允许 file
        path = target[5:]
        if path.startswith("///"):
            path = path[2:]
        if not Path(path).is_file():
            return BrowserResult(False, plan.mode, message=f"模拟页不存在: {path}")
    else:
        try:
            assert_public_http_url(target)
        except Exception as exc:
            return BrowserResult(False, plan.mode, message=str(exc))

    if plan.mode == "MANUAL_ONLY" and not file_url:
        return BrowserResult(
            False,
            plan.mode,
            status="needs_manual",
            message="站点策略为人工；不自动填表",
            requires_human=plan.requires_human or ["请打开官网人工填写"],
        )
    if not _playwright_available():
        return BrowserResult(
            False,
            plan.mode,
            status="blocked",
            message="Playwright 未安装；无法执行实机填表",
            requires_human=plan.requires_human,
        )

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return BrowserResult(False, plan.mode, status="blocked", message=str(exc))

    warnings = list(plan.warnings)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            if target.startswith("file:"):
                page.goto(target)
            else:
                page.goto(target, wait_until="domcontentloaded", timeout=30000)
            for f in plan.fields:
                sel = f"#{f.field_name}, [name='{f.field_name}']"
                try:
                    page.fill(sel, f.value, timeout=3000)
                except Exception:
                    warnings.append(f"字段未找到: {f.field_name}")
            receipt = None
            status = "prefilled"
            if submit and plan.mode != "MANUAL_ONLY":
                try:
                    page.click("#submit_btn, button[type=submit]")
                    page.wait_for_selector("#receipt_code", timeout=5000)
                    receipt = page.inner_text("#receipt_code").strip() or None
                    status = "confirmed" if receipt else "unknown"
                except Exception as exc:
                    status = "unknown"
                    warnings.append(f"提交结果未知: {exc}")
            browser.close()
            return BrowserResult(
                True,
                plan.mode,
                receipt_code=receipt,
                status=status,
                message="浏览器预填完成",
                warnings=warnings,
                requires_human=plan.requires_human,
            )
    except Exception as exc:
        return BrowserResult(False, plan.mode, status="failed", message=str(exc))


def run_prefill_for_round(
    round_: CampaignRound,
    profile: Profile,
    *,
    file_url: str | None = None,
    submit: bool = False,
) -> BrowserResult:
    plan = build_prefill_plan(round_, profile)
    return fill_form_with_playwright(plan, file_url=file_url, submit=submit)
