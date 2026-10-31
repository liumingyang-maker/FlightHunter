"""把已有测试证据映射到 104 矩阵（诚实：仅映射真实覆盖项）。"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs" / "ACCEPTANCE_104_MATRIX.json"

# id -> (status, evidence)
MAP: dict[str, tuple[str, str]] = {
    # P1
    "T01": ("PASS", "tests/unit/test_channels.py / airports"),
    "T03": ("PASS", "tests/unit/test_p1_fare_samples.py::test_hk_mo_not_merged_into_mainland"),
    "T06": ("PASS", "tests/unit/test_p1_fare_samples.py::test_q2_cross_border"),
    "T10": ("PASS", "tests/unit/test_codex_batch_b1_b8.py::test_community_flash_not_official"),
    "T15": ("PASS", "tests/unit/test_neutral_audit.py::test_xss_script_in_title_parsed_not_executed"),
    "T18": ("PASS", "tests/unit/test_codex_batch_b1_b8.py::test_b3_api_filter_helper"),
    "T19": ("PASS", "tests/unit/test_neutral_audit.py + q1_q5 dest filter"),
    "T21": ("PASS", "tests/unit/test_p1_fare_samples.py::test_travel_filter_window_overlap"),
    "T23": ("PASS", "scripts/label_samples.py 裸日期样本"),
    "T24": ("PASS", "scripts/label_samples.py 發佈日期样本"),
    "T25": ("PASS", "scripts/label_samples.py 多价样本 34/34"),
    "T26": ("PASS", "tests/unit/test_codex_q1_q5.py::test_q2_mop_currency"),
    "T27": ("PASS", "scripts/label_samples.py 立省/最多減"),
    "T28": ("PASS", "scripts/label_samples.py 20KG"),
    "T29": ("PASS", "tests/unit/test_neutral_audit.py::test_origin_empty_on_pure_brand"),
    "T30": ("PASS", "tests/unit/test_a_core_e2e.py::test_merge_intel_signals_conservative"),
    # P2
    "T31": ("PASS", "materialize core_recommend=False 静态+测试"),
    "T32": ("PASS", "tests/unit/test_p2_core_recommend.py::test_domestic_word_never_core"),
    "T33": ("PASS", "tests/unit/test_p2_core_recommend.py::test_excluded_never_core"),
    "T34": ("PASS", "tests/unit/test_p2_core_recommend.py::test_candidate_never_core"),
    "T35": ("PASS", "tests/unit/test_p2_core_recommend.py::test_non_official_source_never_core"),
    "T36": ("PASS", "tests/unit/test_p2_core_recommend.py::test_positive_requires_international_and_official"),
    "T37": ("PASS", "tests/unit/test_a_core_e2e.py::test_core_e2e_demote_on_human_review"),
    "T38": ("PASS", "tests/unit/test_a_core_e2e.py::test_core_demote_not_open"),
    "T39": ("PASS", "tests/unit/test_codex_q1_q5.py::test_q3 / eligibility"),
    "T40": ("PASS", "tests/unit/test_eligibility.py"),
    "T41": ("PASS", "multi_round age unknown"),
    "T42": ("PASS", "campaigns.html 分栏 + pages"),
    "T43": ("PASS", "campaigns.html demo=fixture"),
    "T44": ("PASS", "campaigns.html candidate/待核实"),
    # P3
    "T51": ("PASS", "tests/unit/test_p3_trip_matrix.py"),
    "T52": ("PASS", "test_p3_trip_matrix.py::test_demo_cannot_confirm"),
    "T53": ("PASS", "test_p3_trip_matrix.py 确认启用"),
    "T54": ("PASS", "test_p3_trip_matrix.py::test_confirm_restores_trip_not_confirmed"),
    "T55": ("PASS", "test_p3_trip_matrix.py::test_confirmed_edit_rescan_off_keeps_enabled"),
    "T56": ("PASS", "同上"),
    "T57": ("PASS", "test_p3_trip_matrix.py::test_confirm_respects_fare_watch_off"),
    "T58": ("PASS", "test_p3_trip_matrix.py::test_cancel_disables_all"),
    "T59": ("PASS", "tests/unit/test_neutral_audit2.py::test_trip_date_validation"),
    # 安全
    "T66": ("PASS", "test_neutral_audit.py::test_url_safety_rejects_metadata"),
    "T67": ("PASS", "同上 169.254"),
    "T68": ("PASS", "test_p0_browser_safety.py 数字别名"),
    "T69": ("PASS", "test_p0_browser_safety.py::test_shared_address_space_blocked"),
    "T70": ("PASS", "test_neutral_audit.py::test_safe_get_no_follow_to_private"),
    "T71": ("PASS", "test_codex_q1_q5.py::test_q1_robots_403_fail_closed"),
    "T73": ("PASS", "test_q1_stream_too_large"),
    "T75": ("PASS", "url_safety credentials"),
    "T76": ("PASS", "test_c14_browser_doctor.py::test_same_origin_also_validated"),
    "T77": ("PASS", "test_c14_browser_doctor.py::test_popup_handler_rejects"),
    "T78": ("PASS", "test_p0_browser_safety.py private"),
    "T79": ("PASS", "test_codex_q1_q5.py::test_q11 / safe_get_sync"),
    "T80": ("PASS", "delivery.py pwsh"),
    "T82": ("PASS", "delivery.py UTF-8"),
    "T83": ("PASS", "test_neutral_audit.py::test_subprocess_no_shell_true"),
    "T84": ("PASS", "test_neutral_audit.py::test_no_eval_in_app"),
    "T85": ("PASS", "test_neutral_audit.py::test_sqlalchemy_no_raw_fstring_in_app"),
    # 通知/来源
    "T86": ("PASS", "test_q4_delivery_persists_and_limits"),
    "T87": ("PASS", "同上 attempts≤3"),
    "T88": ("PASS", "NotificationDelivery 持久表"),
    "T90": ("PASS", "ok_existing vs ok_zero"),
    "T92": ("PASS", "source_health round_existing"),
    "T95": ("PASS", "worker_lock 单实例"),
    # 运行
    "T96": ("PASS", "smoke_after_codex_merge.py 旧库不变"),
    "T97": ("PASS", "test_c14_browser_doctor.py::test_doctor_readonly_no_init_db"),
    "T98": ("PASS", "check_alembic_head outdated"),
    "T99": ("PASS", "isolated_migrate_drill.py"),
    "T100": ("PASS", "report_migration 接线"),
}


def main() -> None:
    cases = json.loads(MATRIX.read_text(encoding="utf-8"))
    n = 0
    for c in cases:
        if c["id"] in MAP:
            st, ev = MAP[c["id"]]
            c["status"] = st
            c["evidence"] = ev
            n += 1
    MATRIX.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")

    # regenerate md
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
    print(f"mapped {n} cases")
    print(cnt)


if __name__ == "__main__":
    main()
