"""Benefit 领域服务：创建 offer、领取、卡包、指南。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import (
    BenefitClaimOutcomeUnknown,
    ErrorCode,
    FlightHunterError,
    NotFoundError,
    ValidationError,
)
from app.core.ids import idempotency_key, new_id
from app.core.state import (
    BENEFIT_CLAIM_TRANSITIONS,
    BenefitClaimStatus,
    WalletItemState,
    assert_transition,
)
from app.models import (
    BenefitClaim,
    BenefitOffer,
    RedemptionGuide,
    WalletItem,
)
from app.schemas.domain import BenefitClaimStart, BenefitOfferCreate


def create_benefit_offer(session: Session, payload: BenefitOfferCreate) -> BenefitOffer:
    if payload.date_certainty not in (
        "confirmed_for_dates",
        "historical_reference",
        "not_yet_announced",
        "unconfirmed",
    ):
        raise ValidationError("date_certainty 非法")

    offer = BenefitOffer(
        id=new_id(),
        organizer_name=payload.organizer_name,
        title=payload.title,
        category=payload.category,
        claim_method=payload.claim_method.value
        if hasattr(payload.claim_method, "value")
        else str(payload.claim_method),
        official_url=payload.official_url,
        country_codes=json.dumps(payload.country_codes),
        city_codes=json.dumps(payload.city_codes),
        claim_opens_at_local=payload.claim_window.opens_at_local if payload.claim_window else None,
        claim_closes_at_local=payload.claim_window.closes_at_local
        if payload.claim_window
        else None,
        booking_opens_at_local=(
            payload.booking_window.opens_at_local if payload.booking_window else None
        ),
        booking_closes_at_local=(
            payload.booking_window.closes_at_local if payload.booking_window else None
        ),
        redeem_starts_at_local=(
            payload.redemption_window.starts_at_local if payload.redemption_window else None
        ),
        redeem_ends_at_local=(
            payload.redemption_window.ends_at_local if payload.redemption_window else None
        ),
        event_starts_at_local=(
            payload.event_window.starts_at_local if payload.event_window else None
        ),
        event_ends_at_local=(payload.event_window.ends_at_local if payload.event_window else None),
        window_timezone=(
            (payload.claim_window and payload.claim_window.timezone)
            or (payload.redemption_window and payload.redemption_window.timezone)
        ),
        date_certainty=payload.date_certainty,
        conditions=json.dumps(payload.conditions, ensure_ascii=False),
        face_value_min=payload.face_value.min if payload.face_value else None,
        face_value_max=payload.face_value.max if payload.face_value else None,
        face_value_currency=payload.face_value.currency if payload.face_value else None,
        offer_status="candidate",
        source_id=payload.source_id,
        source_url=payload.source_url,
        demo_only=payload.demo_only,
    )
    session.add(offer)
    session.flush()
    return offer


def start_benefit_claim(
    session: Session,
    payload: BenefitClaimStart,
    *,
    allow_auto: bool = False,
) -> BenefitClaim:
    """启动领券。默认 PREFILL_AND_REVIEW；AUTO 需站点授权且 allow_auto。"""
    offer = session.get(BenefitOffer, payload.offer_id)
    if offer is None:
        raise NotFoundError("优惠不存在", details={"offer_id": payload.offer_id})
    if offer.offer_status in ("withdrawn", "expired"):
        raise FlightHunterError(
            ErrorCode.BENEFIT_REVOKED,
            "优惠已撤回或过期，无法领取",
            details={"offer_status": offer.offer_status},
        )

    conditions = json.loads(offer.conditions or "{}")
    if conditions.get("requires_payment") is True:
        raise FlightHunterError(
            ErrorCode.BENEFIT_PAYMENT_REQUIRED,
            "该优惠需要付费，禁止自动领取；请走人工渠道",
        )

    mode = payload.automation_mode
    if mode == "AUTO_ALLOWED":
        if not allow_auto:
            raise FlightHunterError(
                ErrorCode.BENEFIT_AUTOMATION_FORBIDDEN,
                "未启用该站点自动领券授权",
            )
        if offer.claim_method not in ("ACCOUNT_CLAIM", "PUBLIC_DISPLAY"):
            raise FlightHunterError(
                ErrorCode.BENEFIT_AUTOMATION_FORBIDDEN,
                "当前领取方式不支持自动领取",
            )

    profile_scope = payload.profile_id or "anonymous"
    household = payload.household_scope or "solo"
    key = idempotency_key(offer.id, "local", profile_scope, household, "once")

    existing = session.scalar(select(BenefitClaim).where(BenefitClaim.idempotency_key == key))
    if existing:
        if existing.status in (
            BenefitClaimStatus.UNKNOWN.value,
            BenefitClaimStatus.SUBMITTING.value,
        ):
            raise BenefitClaimOutcomeUnknown(
                "上次领取结果未知或进行中，禁止再次领取",
                details={"claim_id": existing.id, "status": existing.status},
            )
        if existing.status == BenefitClaimStatus.CLAIMED.value:
            return existing

    if existing is None:
        claim = BenefitClaim(
            id=new_id(),
            offer_id=offer.id,
            profile_id=payload.profile_id,
            account_scope_key="local",
            profile_scope=profile_scope,
            issuance_period_key="once",
            idempotency_key=key,
            automation_mode=mode,
            status=BenefitClaimStatus.PREPARED.value
            if offer.claim_method != "PUBLIC_DISPLAY"
            else BenefitClaimStatus.AVAILABLE.value,
            manual_review_required=True,
        )
        session.add(claim)
        session.flush()
    else:
        claim = existing
        assert_transition(
            "benefit_claim",
            BenefitClaimStatus(claim.status),
            BenefitClaimStatus.PREPARED,
            BENEFIT_CLAIM_TRANSITIONS,
        )
        claim.status = BenefitClaimStatus.PREPARED.value
        session.flush()

    # 公开展示型：只进卡包 saved，不建立领取成功回执
    if offer.claim_method == "PUBLIC_DISPLAY":
        ensure_wallet_saved(session, offer, claim)
    return claim


def begin_claim_submit(session: Session, claim_id: str) -> BenefitClaim:
    """进入 submitting；仅在请求确实可能发出时调用。"""
    claim = session.get(BenefitClaim, claim_id)
    if claim is None:
        raise NotFoundError("领取记录不存在")
    if claim.status == BenefitClaimStatus.SUBMITTING.value:
        return claim
    assert_transition(
        "benefit_claim",
        BenefitClaimStatus(claim.status),
        BenefitClaimStatus.SUBMITTING,
        BENEFIT_CLAIM_TRANSITIONS,
    )
    claim.status = BenefitClaimStatus.SUBMITTING.value
    claim.last_submitted_at_utc = datetime.now(UTC)
    session.flush()
    return claim


def mark_claim_unknown(session: Session, claim_id: str) -> BenefitClaim:
    claim = session.get(BenefitClaim, claim_id)
    if claim is None:
        raise NotFoundError("领取记录不存在")
    if claim.status == BenefitClaimStatus.UNKNOWN.value:
        return claim
    if claim.status in (
        BenefitClaimStatus.PREPARED.value,
        BenefitClaimStatus.AWAITING_REVIEW.value,
    ):
        claim = begin_claim_submit(session, claim_id)
    assert_transition(
        "benefit_claim",
        BenefitClaimStatus(claim.status),
        BenefitClaimStatus.UNKNOWN,
        BENEFIT_CLAIM_TRANSITIONS,
    )
    claim.status = BenefitClaimStatus.UNKNOWN.value
    claim.error_code = ErrorCode.BENEFIT_CLAIM_OUTCOME_UNKNOWN.value
    claim.last_submitted_at_utc = datetime.now(UTC)
    claim.manual_review_required = True
    session.flush()
    return claim


def confirm_claimed(
    session: Session,
    claim_id: str,
    *,
    receipt_reference: str | None = None,
) -> BenefitClaim:
    """仅在有官方账户券列表/编号/确认邮件/用户逐项核实后调用。HTTP 200 不够。"""
    claim = session.get(BenefitClaim, claim_id)
    if claim is None:
        raise NotFoundError("领取记录不存在")
    if not receipt_reference:
        raise FlightHunterError(
            ErrorCode.RECEIPT_NOT_VERIFIED,
            "缺少可核验领取凭据，不能标记为 claimed",
        )
    if claim.status in (
        BenefitClaimStatus.PREPARED.value,
        BenefitClaimStatus.AWAITING_REVIEW.value,
    ):
        claim = begin_claim_submit(session, claim_id)
    assert_transition(
        "benefit_claim",
        BenefitClaimStatus(claim.status),
        BenefitClaimStatus.CLAIMED,
        BENEFIT_CLAIM_TRANSITIONS,
    )
    claim.status = BenefitClaimStatus.CLAIMED.value
    claim.receipt_reference = receipt_reference
    claim.manual_review_required = False
    session.flush()

    offer = session.get(BenefitOffer, claim.offer_id)
    if offer:
        ensure_wallet_claimed(session, offer, claim)
    return claim


def ensure_wallet_saved(
    session: Session, offer: BenefitOffer, claim: BenefitClaim | None
) -> WalletItem:
    existing = session.scalar(
        select(WalletItem).where(
            WalletItem.offer_id == offer.id,
            WalletItem.claim_id == claim.id if claim else WalletItem.claim_id.is_(None),
        )
    )
    if existing:
        return existing
    item = WalletItem(
        id=new_id(),
        offer_id=offer.id,
        claim_id=claim.id if claim else None,
        state=WalletItemState.SAVED.value
        if offer.claim_method != "APP_ONLY"
        else WalletItemState.DYNAMIC_APP_REQUIRED.value,
        official_url=offer.official_url,
        expires_at_local=offer.redeem_ends_at_local,
    )
    session.add(item)
    session.flush()
    return item


def ensure_wallet_claimed(session: Session, offer: BenefitOffer, claim: BenefitClaim) -> WalletItem:
    item = session.scalar(
        select(WalletItem).where(
            WalletItem.offer_id == offer.id,
            WalletItem.claim_id == claim.id,
        )
    )
    if item is None:
        item = WalletItem(
            id=new_id(),
            offer_id=offer.id,
            claim_id=claim.id,
            state=WalletItemState.CLAIMED.value,
            official_url=offer.official_url,
            expires_at_local=offer.redeem_ends_at_local,
        )
        session.add(item)
    else:
        item.state = WalletItemState.CLAIMED.value
    session.flush()
    return item


def generate_guide(session: Session, offer_id: str) -> RedemptionGuide:
    """基于 offer 已有字段生成中文使用说明；未知字段显式列出。"""
    offer = session.get(BenefitOffer, offer_id)
    if offer is None:
        raise NotFoundError("优惠不存在")

    conditions: dict[str, Any] = json.loads(offer.conditions or "{}")
    unknown: list[str] = []
    warnings: list[str] = []
    claim_steps: list[str] = []
    use_steps: list[str] = []

    if offer.claim_method == "PUBLIC_DISPLAY":
        claim_steps.append("打开官方页面查看/展示券码或打印优惠信息")
        claim_steps.append("无需创建账户领取；保存官方入口即可")
    elif offer.claim_method == "ACCOUNT_CLAIM":
        claim_steps.append("登录官方账户（由你本人操作）")
        claim_steps.append("在活动页点击领取并确认账户内已出现该券")
    elif offer.claim_method == "APP_ONLY":
        claim_steps.append("安装官方 App 后在 App 内领取")
        warnings.append("动态码依赖官方 App，不可用静态截图替代")
    else:
        claim_steps.append("按官方页面说明完成领取")
        unknown.append("claim_method 细节待核实")

    use_steps.append("出行当日或商家允许的时段到店/下单")
    if conditions.get("payment_network"):
        use_steps.append(f"结账时使用符合条件的支付网络：{conditions['payment_network']}")
    else:
        unknown.append("eligible_payment")

    if conditions.get("minimum_spend") is None:
        unknown.append("minimum_spend")
    if offer.date_certainty != "confirmed_for_dates":
        unknown.append("date_certainty_not_confirmed")
        warnings.append("有效期尚未官方确认，出发前请再次核对")

    json.dumps(conditions, ensure_ascii=False)
    payload = {
        "offer_title": offer.title,
        "claim_steps": claim_steps,
        "use_steps": use_steps,
        "conditions": conditions,
        "face_value": (
            f"{offer.face_value_min}~{offer.face_value_max} {offer.face_value_currency}"
            if offer.face_value_min is not None or offer.face_value_max is not None
            else "金额未知"
        ),
        "warnings": warnings,
    }

    existing = session.scalar(
        select(RedemptionGuide).where(
            RedemptionGuide.offer_id == offer_id,
            RedemptionGuide.language == "zh-CN",
        )
    )
    now = datetime.now(UTC)
    if existing:
        existing.verified_at_utc = now
        existing.payload_json = json.dumps(payload, ensure_ascii=False)
        existing.unknown_fields = json.dumps(unknown)
        existing.stale = False
        existing.evidence_version_hash = offer.rules_version_hash
        session.flush()
        return existing

    guide = RedemptionGuide(
        id=new_id(),
        offer_id=offer_id,
        language="zh-CN",
        verified_at_utc=now,
        evidence_version_hash=offer.rules_version_hash,
        payload_json=json.dumps(payload, ensure_ascii=False),
        stale=False,
        unknown_fields=json.dumps(unknown),
    )
    session.add(guide)
    session.flush()
    return guide


def save_wallet_private_code(
    session: Session,
    settings,
    *,
    wallet_item_id: str,
    plaintext_code: str,
) -> WalletItem:
    """加密写入卡包私密码；日志/导出不得出现明文。"""
    from app.services.wallet.crypto import encrypt_secret

    item = session.get(WalletItem, wallet_item_id)
    if item is None:
        raise NotFoundError("卡包条目不存在")
    if not plaintext_code:
        raise ValidationError("空券码")
    item.private_code_encrypted = encrypt_secret(settings, plaintext_code)
    session.flush()
    return item


def load_wallet_private_code(session: Session, settings, wallet_item_id: str) -> str | None:
    from app.services.wallet.crypto import decrypt_secret

    item = session.get(WalletItem, wallet_item_id)
    if item is None or not item.private_code_encrypted:
        return None
    return decrypt_secret(settings, item.private_code_encrypted)


def list_wallet(session: Session) -> list[WalletItem]:
    return list(session.scalars(select(WalletItem)).all())
