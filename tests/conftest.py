import os,sys,json
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0,_ROOT)
sys.path.insert(0,os.path.join(_ROOT,'backend'))
os.environ.setdefault('DATABASE_URL','sqlite:////tmp/coldchain_test.db')
os.environ.setdefault('REDIS_URL','redis://localhost:6379/0')
os.environ.setdefault('JWT_SECRET','test-secret-3102')
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from src.config.database import Base
import src.config.database as dbmod
from src.main import app
from src.services import queue
class FakeQueue:
 def __init__(self):self.q=[]
 def queue_study(self,study_id):self.q.append(int(study_id))
 def ping(self):return True
fake_queue=FakeQueue()
queue.queue_study=fake_queue.queue_study
queue.ping=fake_queue.ping
from src.utils.security import hash_password
from src.models.entities import User,Shipment,Sample,SampleIdentity,IdentityMember,IdentityCorrection,MergeRequest,Recommendation
engine=create_engine('sqlite:////tmp/coldchain_test.db',connect_args={'check_same_thread':False})
TestSession=sessionmaker(bind=engine,expire_on_commit=False)
dbmod.engine=engine;dbmod.Session=TestSession
import src.config.database as dbcfg
dbcfg.engine=engine;dbcfg.Session=TestSession
@pytest.fixture(autouse=True)
def fresh_db():
 Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
 fake_queue.q.clear()
 with TestSession() as s:
  for role in ('admin','analyst','viewer'):
   s.add(User(email=role+'@demo.local',role=role,password=hash_password('Demo123!')))
  sh1=Shipment(code='C-001',route='线路1',zone='冷藏',driver='d1')
  sh2=Shipment(code='C-002',route='线路2',zone='冷藏',driver='d2')
  sh3=Shipment(code='F-001',route='线路3',zone='冷冻',driver='d3')
  s.add_all([sh1,sh2,sh3]);s.flush()
  s.add_all([
   Sample(shipment_id=sh1.id,code='S-A',exposure=10,excursions=1,loss=2.0),
   Sample(shipment_id=sh2.id,code='S-B',exposure=20,excursions=2,loss=3.0),
   Sample(shipment_id=sh1.id,code='S-C',exposure=12,excursions=1,loss=2.5),
   Sample(shipment_id=sh2.id,code='S-D',exposure=30,excursions=3,loss=4.5),
   Sample(shipment_id=sh3.id,code='S-F',exposure=15,excursions=1,loss=4.0),
  ])
  s.commit()
 yield
@pytest.fixture
def client():
 def override():
  with TestSession() as s:yield s
 app.dependency_overrides[dbmod.db]=override
 yield TestClient(app)
 app.dependency_overrides.clear()
def tok(client,role='analyst'):
 r=client.post('/auth/login',json={'email':role+'@demo.local','password':'Demo123!'})
 return r.json()['token']
def h(client,role='analyst'):return {'Authorization':'Bearer '+tok(client,role)}
def rid(prefix,n):return f'{prefix}-{n:08d}-reqid'
def get_ids(s):
 return {m.sample_id:m.identity_id for m in s.query(IdentityMember).filter(IdentityMember.left_version.is_(None)).all()}
