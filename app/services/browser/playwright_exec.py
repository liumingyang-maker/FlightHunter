"""Playwright 执行器：强制人工确认边界。

- PREFILL_AND_REVIEW：永不自动 submit
- 仅 AUTO_ALLOWED + explicit_submit_consent=True 且 file 模拟站/已授权 http 才可 submit
- 远程 http(s) 默认仍不自动 submit（需单独站点授权策略）
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
    submitted: bool = False


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
    explicit_submit_consent: bool = False,
) -> BrowserResult:
    """预填表单。自动提交仅允许显式同意且模式 AUTO_ALLOWED。

    file:// 模拟站可用 explicit_submit_consent 做本地 E2E。
    """
    target = file_url or plan.target_url
    is_local_mock = bool(file_url and file_url.startswith("file:"))
    if is_local_mock:
        path = file_url[5:]
        if path.startswith("///"):
            path = path[2:]
        if not Path(path).is_file():
            return BrowserResult(False, plan.mode, message=f"模拟页不存在: {path}")
    else:
        try:
            assert_public_http_url(target)
        except Exception as exc:
            return BrowserResult(False, plan.mode, message=str(exc))

    if plan.mode == "MANUAL_ONLY":
        return BrowserResult(
            False,
            plan.mode,
            status="needs_manual",
            message="站点策略为人工；不自动填表提交",
            requires_human=plan.requires_human or ["请打开官网人工填写"],
        )

    # 人审模式禁止自动提交
    will_submit = False
    if submit:
        if plan.mode != "AUTO_ALLOWED":
            return BrowserResult(
                False,
                plan.mode,
                status="needs_human",
                message="PREFILL_AND_REVIEW 禁止自动提交；请人工确认后提交",
                requires_human=[*plan.requires_human, "请人工点击提交"],
                submitted=False,
            )
        if not explicit_submit_consent:
            return BrowserResult(
                False,
                plan.mode,
                status="needs_human",
                message="缺少 explicit_submit_consent；禁止自动提交",
                requires_human=["请提供单次提交授权"],
                submitted=False,
            )
        if not is_local_mock:
            # 真实外站：即使 AUTO_ALLOWED 也不自动 submit（上线前门槛）
            return BrowserResult(
                False,
                plan.mode,
                status="blocked",
                message="真实外站自动提交已关闭；请人工完成最终提交",
                requires_human=["请在浏览器中人工提交"],
                submitted=False,
            )
        will_submit = True

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
                    loc = page.locator(sel).first
                    tag = loc.evaluate("e => e.tagName.toLowerCase()") if loc.count() else ""
                    if tag == "select":
                        loc.select_option(f.value, timeout=3000)
                    elif tag == "input":
                        itype = loc.get_attribute("type") or "text"
                        if itype == "checkbox":
                            if f.value.lower() in ("1", "true", "yes"):
                                loc.check(timeout=2000)
                            else:
                                loc.uncheck(timeout=2000)
                        else:
                            loc.fill(f.value, timeout=3000)
                    else:
                        loc.fill(f.value, timeout=3000)
                except Exception:
                    warnings.append(f"字段未找到: {f.field_name}")
            receipt = None
            status = "prefilled"
            if will_submit:
                page.click("#submit_btn, button[type=submit]")
                page.wait_for_selector("#receipt_code", timeout=5000)
                receipt = page.inner_text("#receipt_code").strip() or None
                status = "confirmed" if receipt else "unknown"
            browser.close()
            return BrowserResult(
                True,
                plan.mode,
                receipt_code=receipt,
                status=status,
                message="浏览器预填完成",
                warnings=warnings,
                requires_human=plan.requires_human,
                submitted=will_submit,
            )
    except Exception as exc:
        return BrowserResult(
            False, plan.mode, status="failed", message=str(exc), submitted=False
        )


def run_prefill_for_round(
    round_: CampaignRound,
    profile: Profile,
    *,
    file_url: str | None = None,
    submit: bool = False,
    explicit_submit_consent: bool = False,
) -> BrowserResult:
    plan = build_prefill_plan(round_, profile)
    return fill_form_with_playwright(
        plan,
        file_url=file_url,
        submit=submit,
        explicit_submit_consent=explicit_submit_consent,
    )
