"""端到端冒烟：覆盖归并→更正→研究去重→签核→转待复核→拆回的完整业务链。"""
import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0,os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'backend'))
os.environ['DATABASE_URL']='sqlite:////tmp/coldchain_e2e.db'
os.environ['REDIS_URL']='redis://localhost:6379/0'
os.environ['JWT_SECRET']='e2e-secret'
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.config.database import Base
import src.config.database as dbmod
from src.services import queue
from src.main import app
from src.utils.security import hash_password
from src.models.entities import User,Shipment,Sample,Study,Recommendation,SampleIdentity,IdentityMember
eng=create_engine('sqlite:////tmp/coldchain_e2e.db',connect_args={'check_same_thread':False})
TS=sessionmaker(bind=eng,expire_on_commit=False)
dbmod.engine=eng;dbmod.Session=TS
queue.queue_study=lambda i:None;queue.ping=lambda:True
Base.metadata.drop_all(eng);Base.metadata.create_all(eng)
def ov():
 with TS() as s:yield s
app.dependency_overrides[dbmod.db]=ov
c=TestClient(app)
with TS() as s:
 for role in ('admin','analyst','viewer'):s.add(User(email=role+'@demo.local',role=role,password=hash_password('Demo123!')))
 s.commit()
 z1=Shipment(code='Z1',route='线1',zone='冷藏',driver='d');z2=Shipment(code='Z2',route='线2',zone='冷藏',driver='d')
 z3=Shipment(code='H1',route='线3',zone='冷冻',driver='d');s.add_all([z1,z2,z3]);s.flush()
 for i,(sh,ex,lo) in enumerate([(z1,10,2.0),(z2,20,3.0),(z1,30,4.0),(z2,40,5.0),(z3,15,2.0)]):
  s.add(Sample(shipment_id=sh.id,code=f'E{i}',exposure=ex,excursions=i+1,loss=lo))
 s.commit()
def login(role):
 t=c.post('/auth/login',json={'email':role+'@demo.local','password':'Demo123!'}).json()['token']
 return {'Authorization':'Bearer '+t}
ha,hl=login('admin'),login('analyst')
# 1. 目录惰性建档
cat=c.get('/identities',headers=hl).json();assert len(cat)==5 and all(i['status']=='unmerged' for i in cat)
# 2. 跨温区拒绝
with TS() as s:ids=[s.query(Sample).filter_by(code=x).first().id for x in ('E0','E4')]
r=c.post('/identities/merge',headers=hl,json={'request_id':'e2e-req-01','sample_ids':ids,'choices':{}})
assert r.status_code==409 and '跨温区' in r.text
# 3. 预览冲突
with TS() as s:ab=[s.query(Sample).filter_by(code=x).first().id for x in ('E0','E1')]
pv=c.post('/identities/merge-preview',headers=hl,json={'request_id':'e2e-req-pv','sample_ids':ab}).json()
assert len(pv['conflicts'])==3
# 4. 不带 choices 拒绝
r=c.post('/identities/merge',headers=hl,json={'request_id':'e2e-req-02','sample_ids':ab,'choices':{}})
assert r.status_code==409
# 5. 正式归并
ch={f:{'sample_id':ab[1]} for f in ('exposure','loss')};ch['excursions']={'sample_id':ab[0]}
m=c.post('/identities/merge',headers=hl,json={'request_id':'e2e-req-03','sample_ids':ab,'choices':ch}).json()
assert m['identity_id']==1 and m['version']==2
# 6. 原记录被更正、代表值重算
with TS() as s:
 e0=s.query(Sample).filter_by(code='E0').first();e1=s.query(Sample).filter_by(code='E1').first()
 assert e0.exposure==20 and e0.loss==3.0 and e1.excursions==1
 ident=s.get(SampleIdentity,1);assert ident.status=='merged' and ident.exposure==20
# 7. 同请求重试不重复变更
again=c.post('/identities/merge',headers=hl,json={'request_id':'e2e-req-03','sample_ids':ab,'choices':ch}).json()
assert again==m
# 8. 研究按身份去重（冷藏 4 样本→3 身份），快照冻结
st=c.post('/studies',headers=hl,json={'name':'e2e研究','zone':'冷藏','feature':'exposure'}).json()
snap=st['result']['snapshot'];assert len(snap)==3
assert all('field_sources' in row and 'identity_id' in row for row in snap)
# 9. worker 分析可跑通
from src.services.analysis import analyze
with TS() as s:
 row=s.get(Study,st['id']);res=analyze(row.result['snapshot'],'exposure')
 assert res['n']==3;row.state='done';row.result={**res,'snapshot':row.result['snapshot']};s.commit()
# 10. 建议起草+签核
rec=c.post('/recommendations',headers=hl,json={'study_id':st['id'],'note':'e2e 复核线路装卸等待时长的建议','owner':'主管'}).json()
assert c.post(f"/recommendations/{rec['id']}/approve",headers=ha).status_code==200
# 11. 再次身份变化（把 E2 并入身份1）→ 已签核转待复核
with TS() as s:e2=s.query(Sample).filter_by(code='E2').first().id
r2=c.post('/identities/merge',headers=hl,json={'request_id':'e2e-req-04','sample_ids':[ab[0],e2],
 'choices':{'exposure':{'sample_id':e2},'excursions':{'sample_id':ab[0]},'loss':{'sample_id':e2}}})
m2=r2.json()
assert m2['review_reopened']==1
with TS() as s:assert s.get(Recommendation,rec['id']).status=='review'
# 12. 待复核不能直接签核
assert c.post(f"/recommendations/{rec['id']}/approve",headers=ha).status_code==409
# 13. 旧研究快照原样可读
old=c.get(f"/studies/{st['id']}",headers=hl).json()
assert len(old['result']['snapshot'])==3
# 14. 过期拆回拒绝，正确版本拆回成功
stale=c.post('/identities/split',headers=hl,json={'request_id':'e2e-req-spbad','identity_id':1,'base_version':1,'retain_sample_ids':[ab[0]]})
assert stale.status_code==409
sp=c.post('/identities/split',headers=hl,json={'request_id':'e2e-req-spok','identity_id':1,'base_version':m2['version'],'retain_sample_ids':[ab[0]]}).json()
assert len(sp['new_identity_ids'])==2
# 15. 拆回保留更正、不恢复签核
with TS() as s:
 assert s.get(SampleIdentity,1).status=='split'
 assert s.get(Recommendation,rec['id']).status=='review'
 e0=s.query(Sample).filter_by(code='E0').first();assert e0.exposure==30
 e1=s.query(Sample).filter_by(code='E1').first();assert e1.exposure==30
# 16. viewer 只读
assert c.post('/identities/merge',headers=login('viewer'),json={'request_id':'e2e-viewer-01','sample_ids':ab,'choices':{}}).status_code==403
print('E2E ALL OK：',{'identities':len(c.get('/identities',headers=hl).json()),'snapshot_identities':len(snap),'reopened':m2['review_reopened'],'split_into':len(sp['new_identity_ids'])})
