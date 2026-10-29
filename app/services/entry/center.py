"""报名中心状态视图。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CampaignRound, EntryAttempt

GROUPS = {
    "可准备": ["not_started", "prepared"],
    "等待你的检查": ["awaiting_review"],
    "需要你完成": ["submitting"],
    "结果未知": ["unknown"],
    "已确认": ["confirmed"],
    "不符合或已结束": ["rejected", "failed", "cancelled"],
}


def entry_center_view(session: Session) -> dict[str, list[dict]]:
    attempts = session.scalars(select(EntryAttempt)).all()
    by_status: dict[str, list[EntryAttempt]] = {k: [] for k in GROUPS}
    for a in attempts:
        for label, statuses in GROUPS.items():
            if a.status in statuses:
                by_status[label].append(a)
                break

    out: dict[str, list[dict]] = {}
    for label, rows in by_status.items():
        items = []
        for a in rows:
            round_ = session.get(CampaignRound, a.round_id)
            why = {
                "not_started": "尚未开始准备报名",
                "prepared": "已准备，等待你检查预填内容",
                "awaiting_review": "浏览器已预填，请确认后提交",
                "submitting": "正在提交，请勿重复点击",
                "unknown": "请求可能已发送但结果未知，禁止自动重试；请人工到官网核实",
                "confirmed": "已有确认凭据",
                "rejected": "官方拒绝",
                "failed": "可证明未发出，可重新准备",
                "cancelled": "已取消",
            }.get(a.status, a.status)
            next_step = {
                "prepared": "打开预填页并核对字段",
                "awaiting_review": "点击提交（由你完成）",
                "unknown": "登录主办方账户或查收确认邮件",
                "failed": "重新预填",
            }.get(a.status, "暂无操作")
            items.append(
                {
                    "attempt_id": a.id,
                    "round_id": a.round_id,
                    "title": round_.title if round_ else None,
                    "status": a.status,
                    "why_stuck": why,
                    "next_step": next_step,
                    "error_code": a.error_code,
                    "has_resubmit_button": False,  # unknown 永不提供自动再提交
                }
            )
        out[label] = items
    return out
