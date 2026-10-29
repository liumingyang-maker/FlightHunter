"""Isolated audit reproductions. No outbound network. Does not modify user source."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from app.config import AppConfig, AuthConfig, Settings, StorageConfig
from app.core.ids import new_id
from app.core.url_safety import assert_public_http_url
from app.db.session import create_db_engine, init_db, make_session_factory
from app.models import Campaign, CampaignRound, Organizer
from app.schemas.domain import FareSignalImport, FareWatchCreate
from app.services.fare.service import (
 create_fare_watch,
 evaluate_alerts_for_match,
 import_signal,
 match_watch_to_deals,
 record_quote,
)
from app.services.verify.service import complete_verify_from_html
from app.web.app import create_app
from app.web.auth import create_session_cookie_value, verify_session_cookie
from fastapi.testclient import TestClient

with tempfile.TemporaryDirectory() as temp:
 settings=Settings(app=AppConfig(demo_mode=True),auth=AuthConfig(enabled=True,api_token='only-for-local-test'),storage=StorageConfig(sqlite_path=str(Path(temp)/'test.sqlite')))
 settings.project_root=temp
 eng=create_db_engine(settings); init_db(eng)
 with make_session_factory(eng)() as db:
  org=Organizer(id=new_id(),name='Sample')
  db.add(org);db.flush()
  camp=Campaign(id=new_id(),organizer_id=org.id,program_key='audit-news',name='Audit')
  db.add(camp); db.flush()
  r=CampaignRound(id=new_id(),campaign_id=camp.id,edition_key='x',title='Win flights',organizer_name='Sample',official_url='https://example.org/campaign',verify_status='candidate')
  db.add(r);db.flush()
  html='<html><head><title>Example news index</title></head><body><p>No purchase necessary to subscribe to a newsletter. Updated 2027-03-01.</p></body></html>'
  complete_verify_from_html(db,r,html,source_url='https://example.org/campaign')
  db.flush()
  print('P001 unrelated HTML at same URL marked:',r.verify_status)

  deal,_=import_signal(db,FareSignalImport(title='Sample community lead',raw_claim_text='arbitrary',origin_airport='CKG',destination_airport='NRT',reported_total=999,party_size=2,deal_types=['flash_sale']))
  watch=create_fare_watch(db,FareWatchCreate(name='w',origin_airports=['CKG'],adults=2,max_total_cost_cny=100))
  quote=record_quote(db,deal_id=deal.id,watch_id=watch.id,provider='totally_unregistered_provider',party_size=2,total_price=500,origin='LAX',destination='JFK',quote_expiry_utc=None,availability_confirmed=False)
  db.flush()
  matches=match_watch_to_deals(db,watch)
  alert=evaluate_alerts_for_match(db,matches[0],watch=watch)
  print('P002 fake quote:',{'provider':quote.provider,'expiry':str(quote.quote_expiry_utc),'available':quote.availability_confirmed,'quote_route':quote.origin+'-'+quote.destination,'deal_route':deal.origin+'-'+deal.destination,'over_budget':json.loads(matches[0].reason_codes),'alert':alert.alert_level})
  db.commit()
 eng.dispose()

 for host in ('2130706433','0x7f000001','0177.0.0.1','127.1'):
  try: assert_public_http_url('http://'+host+'/'); outcome='ALLOWED'
  except Exception:outcome='BLOCKED'
  print('I10 numeric-localhost URL',host,outcome)

 with TestClient(create_app(settings)) as client:
  print('API anonymous',client.get('/api/v1/profiles').status_code)
  form=client.post('/login',data={'token':'only-for-local-test','next':'https://example.invalid/redirect'},follow_redirects=False)
  print('Login redirect location',form.status_code,form.headers.get('location'))
  auth_cookie=form.cookies.get(settings.auth.session_cookie_name)
  print('Auth cookie accepted server',verify_session_cookie(auth_cookie,settings))
  client.cookies.set(settings.auth.session_cookie_name,auth_cookie)
  print('Authenticated via cookie',client.get('/api/v1/profiles').status_code)
  client.post('/api/v1/auth/logout')
  client.cookies.set(settings.auth.session_cookie_name,auth_cookie)
  print('Cookie replay after logout',client.get('/api/v1/profiles').status_code)
  print('Session signed value stable',create_session_cookie_value(settings)==auth_cookie)
