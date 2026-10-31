"""生成 104 项验收矩阵骨架（可填证据）。基于 PRODUCT_BASELINE 分区。"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "ACCEPTANCE_104_MATRIX.json"
OUT_MD = ROOT / "docs" / "ACCEPTANCE_104_MATRIX.md"

# 104 条验收用例（T01–T104），状态：NOT_TESTED | PASS | FAIL | PARTIAL | BLOCKED
CASES: list[dict] = []


def add(cid: str, cat: str, title: str, method: str, evidence_hint: str = "") -> None:
    CASES.append(
        {
            "id": cid,
            "category": cat,
            "title": title,
            "method": method,
            "status": "NOT_TESTED",
            "evidence": evidence_hint,
            "notes": "",
        }
    )


# ---- P1 情报 30 ----
p1 = [
    ("T01", "出发地多选默认 CKG/TFU/CTU"),
    ("T02", "出发地可增删内地机场"),
    ("T03", "全国出发仅内地不含 HKG/MFM"),
    ("T04", "HKG/MFM 独立勾选不自动并入"),
    ("T05", "国际航线过滤（排除纯内地）"),
    ("T06", "HKG↔PVG 跨境保留"),
    ("T07", "全球错价频道无默认偏好"),
    ("T08", "四频道切换加载正确"),
    ("T09", "情报分类：错价/漏油/促销/社区"),
    ("T10", "社区 flash 不标官方促销"),
    ("T11", "报道价≠可买价文案"),
    ("T12", "无实时报价仍可用"),
    ("T13", "来源链接可点击原文"),
    ("T14", "危险协议链接过滤 javascript:"),
    ("T15", "XSS 标题不执行"),
    ("T16", "过期情报可隐藏"),
    ("T17", "收藏反馈写入 signal_status"),
    ("T18", "反馈筛选 bookmarked 命中"),
    ("T19", "目的地筛选不匹配航司名"),
    ("T20", "类别筛选"),
    ("T21", "travel 日期窗口重叠"),
    ("T22", "发布/发现/旅行分列"),
    ("T23", "裸日期不写 published_at"),
    ("T24", "发佈日期标签写 published_at"),
    ("T25", "多目的地多价不写单一票价"),
    ("T26", "MOP≠HKD 币种"),
    ("T27", "立省/最多減不写票价"),
    ("T28", "20KG 不作 20000"),
    ("T29", "品牌航司不证明出发地"),
    ("T30", "去重合并保守不误合并"),
]
for cid, title in p1:
    add(cid, "P1-情报", title, "单测/标注样本/API")

# ---- P2 抽奖 20 ----
p2 = [
    ("T31", "候选 materialize 不进 core"),
    ("T32", "国内航班不 core"),
    ("T33", "排除大陆不 core"),
    ("T34", "candidate 不 core"),
    ("T35", "社区源不 core"),
    ("T36", "官方+国际+内地出境可 core"),
    ("T37", "human_review 降级 core"),
    ("T38", "closed/unknown 降级 core"),
    ("T39", "资格缺国籍/居住→unknown"),
    ("T40", "资格冲突→ineligible"),
    ("T41", "年龄无官方规则→unknown"),
    ("T42", "页面 verify/类型/出境/核心分栏"),
    ("T43", "demo 标 fixture"),
    ("T44", "非 verified 标待核实"),
    ("T45", "官方链接 vs 线索链接"),
    ("T46", "OCR 日期解析（海报）"),
    ("T47", "HTML/OCR 冲突→人工复核"),
    ("T48", "entry probe 不登录不提交"),
    ("T49", "robots 拒绝时 blocked"),
    ("T50", "自动核验命名 auto_extracted"),
]
for cid, title in p2:
    add(cid, "P2-抽奖", title, "单测/服务流")

# ---- P3 行程 15 ----
p3 = [
    ("T51", "未确认不扫描"),
    ("T52", "demo 不可确认"),
    ("T53", "确认后订阅启用"),
    ("T54", "确认恢复 trip_not_confirmed"),
    ("T55", "已确认编辑不扫停"),
    ("T56", "auto_scan_off 不禁用已有"),
    ("T57", "fare_monitor 尊重 auto_attach"),
    ("T58", "取消行程停订阅"),
    ("T59", "日期校验 end>=start"),
    ("T60", "行程福利匹配国家"),
    ("T61", "城市匹配 unknown 不假匹配"),
    ("T62", "日期窗口相交"),
    ("T63", "城市停留日相交"),
    ("T64", "社区 travel_deal 无国家不全国"),
    ("T65", "领取记录不被编辑清空"),
]
for cid, title in p3:
    add(cid, "P3-行程", title, "矩阵测试")

# ---- 安全 20 ----
sec = [
    ("T66", "私网 URL 拒绝"),
    ("T67", "169.254.169.254 拒绝"),
    ("T68", "数字 IP 别名拒绝"),
    ("T69", "共享地址 100.64 拒绝"),
    ("T70", "公开→私网重定向拒绝且无请求"),
    ("T71", "robots 403 fail-closed"),
    ("T72", "robots 429 fail-closed"),
    ("T73", "流式超限拒绝"),
    ("T74", "Content-Length 超限拒绝"),
    ("T75", "URL 内嵌凭据拒绝"),
    ("T76", "同源请求也 DNS 校验"),
    ("T77", "弹窗默认拒绝"),
    ("T78", "浏览器私网目标拒绝"),
    ("T79", "safe_get 在 loop 内安全"),
    ("T80", "pwsh 非 powershell 5.1"),
    ("T81", "toast Base64 传参无拼接注入"),
    ("T82", "subprocess UTF-8 解码"),
    ("T83", "无 shell=True"),
    ("T84", "无 eval/exec"),
    ("T85", "无 f-string SQL"),
]
for cid, title in sec:
    add(cid, "安全", title, "中立审计/单测")

# ---- 通知/来源 10 ----
ntf = [
    ("T86", "通知成功幂等不重复"),
    ("T87", "失败重试≤3"),
    ("T88", "事件键跨进程持久"),
    ("T89", "长正文状态不丢"),
    ("T90", "ok_existing≠ok_zero"),
    ("T91", "ok_valuable 计有价值"),
    ("T92", "source_health 区分 existing"),
    ("T93", "失败来源 consecutive_failures"),
    ("T94", "403/429 停抓"),
    ("T95", "Worker 单实例锁"),
]
for cid, title in ntf:
    add(cid, "通知/来源", title, "单测/日志")

# ---- 运行/Web 9 ----
rt = [
    ("T96", "Web 启动不改旧库表"),
    ("T97", "doctor 只读"),
    ("T98", "迁移 outdated 提示"),
    ("T99", "迁移 in_sync"),
    ("T100", "CLI report_migration 可见"),
    ("T101", "Web 四频道页可用"),
    ("T102", "campaigns 分栏可用"),
    ("T103", "登录后私有数据"),
    ("T104", "72h 连续采样报告"),
]
for cid, title in rt:
    add(cid, "运行/Web", title, "隔离冒烟/Playwright/72h")


def main() -> None:
    assert len(CASES) == 104, len(CASES)
    OUT.write_text(json.dumps(CASES, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# FlightHunter 104 项验收矩阵",
        "",
        "**口径：** PASS 需证据；NOT_TESTED 诚实标注；禁止假绿。",
        f"**条数：** {len(CASES)}",
        "",
        "| ID | 类别 | 用例 | 方法 | 状态 | 证据 |",
        "|---|---|---|---|---|---|",
    ]
    for c in CASES:
        lines.append(
            f"| {c['id']} | {c['category']} | {c['title']} | {c['method']} | {c['status']} | {c['evidence'] or '—'} |"
        )
    lines.append("")
    lines.append("## 汇总")
    lines.append("")
    from collections import Counter

    cnt = Counter(c["status"] for c in CASES)
    for k, v in cnt.items():
        lines.append(f"- **{k}**: {v}")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT} and {OUT_MD} n={len(CASES)}")
    print(cnt)


if __name__ == "__main__":
    main()
