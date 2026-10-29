"""Offline test of a saved genuine trip against only the app's default sources."""
import sys
import tempfile
import types
from datetime import date
from pathlib import Path

shim=types.ModuleType('feedparser'); shim.parse=lambda _:types.SimpleNamespace(entries=[])
sys.modules['feedparser']=shim
from app.config import Settings, StorageConfig, TripMonitoringConfig
from app.db.session import create_db_engine, ensure_default_sources, init_db, make_session_factory
from app.models import Source, TripScanSubscription
from app.scheduler.jobs import run_due_scans
from app.schemas.domain import TripCreate
from app.services.trips.service import create_trip
from sqlalchemy import select

with tempfile.TemporaryDirectory() as temp:
 s=Settings(storage=StorageConfig(sqlite_path=str(Path(temp)/'t.db')),trip_monitoring=TripMonitoringConfig(enabled=True,auto_register_on_trip_save=True))
 s.project_root=temp
 eng=create_db_engine(s); init_db(eng)
 with make_session_factory(eng)() as db:
  ensure_default_sources(db,s)
  trip=create_trip(db,s,TripCreate(label='日本演示',destination_country_code='JP',local_start_date=date(2027,5,10),local_end_date=date(2027,5,30),timezone='Asia/Tokyo',demo_only=False))
  db.commit()
  print('PROBE_3: registered source modules:',[(x.name,x.module,x.country_code) for x in db.scalars(select(Source)).all()])
  print('PROBE_3: subscription states:',[(x.task_type,x.source_group,x.enabled) for x in db.scalars(select(TripScanSubscription)).all()])
  runs=run_due_scans(db,s,dry_run=False,limit=10)
  db.commit()
  print('PROBE_3: due scan results:',[(r.task_type,r.status,r.result_summary) for r in runs])
 eng.dispose()
