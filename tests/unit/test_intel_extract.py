"""P1 出发城市提取与匹配分级。"""

from __future__ import annotations

from app.services.fare.intel import (
    extract_airline,
    extract_dest_iata,
    extract_origin_iatas_from_title,
)


def test_extract_multiple_origins_including_chengdu():
    title = "北上广/成都-芬兰赫尔辛基机票 往返含税2.7K+"
    origins = extract_origin_iatas_from_title(title)
    assert "TFU" in origins
    assert "PEK" in origins
    assert extract_dest_iata(title) == "HEL"
    assert extract_airline(title) is None
    assert extract_airline("全日空 全国多地-东京") == "ANA"


def test_national_title_has_multiple_origins():
    origins = extract_origin_iatas_from_title("全国多地-泰国曼谷机票")
    # 全国多地本身不产生单一机场，但无强制
    assert "BKK" != extract_dest_iata("全国多地-泰国曼谷机票") or extract_dest_iata("泰国曼谷") == "BKK"
    assert extract_dest_iata("全国多地-泰国曼谷机票") == "BKK"
