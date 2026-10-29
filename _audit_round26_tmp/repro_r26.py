"""Independent, fully offline R25 review boundary reproductions (not product code)."""
from __future__ import annotations
import sys, types, json, asyncio
m=types.ModuleType('feedparser')
m.parse=lambda _: (_ for _ in ()).throw(RuntimeError('feedparser unavailable, RSS parsing not tested'))
sys.modules['feedparser']=m

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.models.base import Base
from app.models import Source, Organizer, Campaign, CampaignRound, TaskRun
from app.adapters.html_fetcher import HttpxFetchAdapter
from app.services.discovery.service import materialize_raffle_candidates, run_discovery
from app.config import Settings
from app.services.ops.status import system_status
from app.services.verify.service import _organizer_domain_ok
from app.core.ids import new_id
from app.core.timeutils import utc_now

engine=create_engine('sqlite+pysqlite:///:memory:')
Base.metadata.create_all(engine)
with Session(engine) as s:
    empty_results=asyncio.run(run_discovery(s, Settings(), module='raffle', dry_run=False, after_fetch=False))
    # Mirrors CLI run_status branch for zero results; no HTTP requests are made.
    empty_status='completed'
    if empty_results and not any(r.get('status') == 'ok' for r in empty_results) and any(r.get('status') in ('failed','denied','manual_only') for r in empty_results):
        empty_status='failed'
    print('NO_SOURCES_CLI_BUG_REPRO',json.dumps({'results':empty_results,'derived_cli_run_status':empty_status},ensure_ascii=False))
    src=Source(id=new_id(),name='Contest Girl 列表',base_url='https://www.contestgirl.com/',kind='community',module='raffle',allowed_fetch_mode='httpx',access_policy='public_fetch',status='active')
    s.add(src);s.flush()
    html="""<html>
    <a href='/contest/mixer'>Win an expensive kitchen mixer contest giveaway!</a>
    <a href='/contest/trip'>Win a round-trip flight to Japan giveaway!</a>
    <a href='/contest/phone'>iPhone giveaway contest</a>
    </html>"""
    parser=object.__new__(HttpxFetchAdapter)
    parsed=parser.parse_raffle(html,url=src.base_url)
    a=materialize_raffle_candidates(s,src,parsed)
    b=materialize_raffle_candidates(s,src,parsed)
    s.flush()
    camp_rows=s.execute(select(CampaignRound,Campaign,Organizer).join(Campaign,CampaignRound.campaign_id==Campaign.id).join(Organizer,Campaign.organizer_id==Organizer.id)).all()
    data={
        'candidate_items_created_first_run': a,
        'candidate_items_created_second_run':b,
        'rows':[{ 'title':r.title,'verify_status':r.verify_status,'category':c.category,'organizer_name':o.name,'organizer_domain':o.official_domain,'official_url':r.official_url,'eligible_for_automatic_verified':_organizer_domain_ok(s,r)} for r,c,o in camp_rows]
    }
    only_non_scan=TaskRun(id=new_id(),task_type='notification_delivery',status='completed',idempotency_key='TEST-notification',dry_run=False,finished_at=utc_now())
    s.add(only_non_scan);s.flush()
    data['last_successful_execute_scan_if_only_notification_completed']=system_status(s)['last_successful_execute_scan_utc']
    print(json.dumps(data,ensure_ascii=False,indent=2))
