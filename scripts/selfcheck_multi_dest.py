"""复验多目的地与通知渠道行。"""
from app.adapters.html_fetcher import (
    extract_route_price_candidates,
    parse_deal_label,
)
from app.services.fare.intel import (
    extract_dest_iata,
    extract_origin_iatas_from_title,
)

label = "香港出发 台湾 HK$800 · 大阪 HK$1500 機票優惠"
routes = extract_route_price_candidates(label)
print("routes", routes)
sig = parse_deal_label(label, page_url="https://example.com/x")
print(
    "sig",
    None
    if sig is None
    else (sig.reported_total, sig.currency, sig.origin_airport, sig.destination_airport),
)
print("origins", extract_origin_iatas_from_title(label))
print("dest", extract_dest_iata(label))

r2 = extract_route_price_candidates("大阪 MOP$1500 機票優惠")
print("mop", r2)
sig2 = parse_deal_label("大阪 MOP$1500 機票優惠", page_url="https://e.com/x")
print("sig2", None if sig2 is None else (sig2.reported_total, sig2.currency))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models import Base, NotificationDelivery
from app.services.notify import delivery as dlv

eng = create_engine("sqlite+pysqlite:///:memory:", future=True)
Base.metadata.create_all(eng)
S = sessionmaker(bind=eng, expire_on_commit=False, future=True)
s = S()


def fail_t(title, body):
    return {"channel": "windows_toast", "status": "failed", "detail": "x"}


dlv.deliver_windows_toast = fail_t
for _ in range(5):
    dlv.send_notification(s, kind="t2", title="failmsg", body="y", event_key="ek2")
for row in s.scalars(
    select(NotificationDelivery).where(NotificationDelivery.event_key == "ek2")
):
    print("deliv", row.channel, row.status, row.attempts)
