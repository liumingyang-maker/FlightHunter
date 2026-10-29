"""Offline feature probes. Does not change FlightHunter source or make network calls.
feedparser shim only avoids missing optional dependency on this isolated host.
"""
import asyncio
import sys
import tempfile
import types
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

if 'feedparser' not in sys.modules:
    shim=types.ModuleType('feedparser'); shim.parse=lambda _: types.SimpleNamespace(entries=[])
    sys.modules['feedparser']=shim

from app.adapters.base import FetchResult, ParsedSignal, SourceAdapter
from app.config import Settings, StorageConfig
from app.core.ids import new_id
from app.db.session import create_db_engine, init_db, make_session_factory
from app.models import CampaignRound, RawCandidate, Source, TaskRun
from app.services.discovery import service as ds
from app.services.ops.status import system_status


class OfflineFixtureAdapter(SourceAdapter):
    name = 'offline-raffle-fixture'
    async def fetch(self,url):
        return FetchResult(ok=True,url=url,final_url=url,status_code=200,content_type='text/html',text='<h1>WIN a round trip flight</h1><p>Free to enter, ends 2026-12-31</p>',content_hash='hash1')
    def parse(self,text,*,url):
        return [ParsedSignal(title='WIN a round trip flight',raw_claim_text='Free to enter, ends 2026-12-31',url=url,confidence='low')]

with tempfile.TemporaryDirectory() as temp:
    root=Path(temp)
    settings=Settings(storage=StorageConfig(sqlite_path=str(root/'t.db')))
    settings.project_root=str(root)
    engine=create_db_engine(settings); init_db(engine)
    factory=make_session_factory(engine)
    with factory() as session:
        now=datetime.now(UTC)
        t=TaskRun(id=new_id(),task_type='benefit_discovery',status='failed',idempotency_key='probe_fail',started_at=now,finished_at=now,dry_run=False)
        session.add(t);session.commit()
        st=system_status(session)
        print('PROBE_1: only failed task exists; reported last_successful_execute_scan_utc=',repr(st['last_successful_execute_scan_utc']))
        print('PROBE_1: task status',t.status)
        assert st['last_successful_execute_scan_utc'] is not None, 'Expected bug was not reproduced'
    with factory() as session:
        src=Source(id=new_id(), name='test official raffle source', base_url='https://example.org/raffle',kind='official_page',module='raffle',status='active',access_policy='public_fetch',allowed_fetch_mode='httpx')
        session.add(src);session.commit()
        prev=ds.adapter_for
        try:
            ds.adapter_for=lambda source,settings: OfflineFixtureAdapter()
            result=asyncio.run(ds.run_discovery(session,settings,module='raffle',dry_run=False,limit=3,persist_signals=True,after_fetch=True,enforce_cooldown=False))
            session.commit()
        finally: ds.adapter_for=prev
        c=session.scalars(select(RawCandidate)).all()
        rounds=session.scalars(select(CampaignRound)).all()
        print('PROBE_2: offline raffle parsed; result=',result)
        print('PROBE_2: raw_candidates=',len(c),'campaign_rounds=',len(rounds))
        assert len(c)>0 and not rounds, 'Expected missing raffle materialization was not reproduced'
    engine.dispose()
print('Both probes reproduced.')
