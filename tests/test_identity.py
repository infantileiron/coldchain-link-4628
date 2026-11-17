import pytest
from tests.conftest import TestSession,h,rid,get_ids
from src.models.entities import Sample,SampleIdentity,IdentityMember,IdentityCorrection,MergeRequest,Study,Recommendation
def test_sample_creation_makes_unmerged_identity(client):
 r=client.get('/identities',headers=h(client))
 assert r.status_code==200
 data=r.json()
 assert len(data)==5
 assert all(i['status']=='unmerged' and i['pair_count']==1 for i in data)
 assert {i['display_code'] for i in data}=={'S-A','S-B','S-C','S-D','S-F'}
def test_preview_reports_conflicts_and_zone(client):
 s=TestSession();ids=get_ids(s)
 a=s.query(Sample).filter_by(code='S-A').first().id
 b=s.query(Sample).filter_by(code='S-B').first().id
 r=client.post('/identities/merge-preview',headers=h(client),json={'request_id':rid('pv',1),'sample_ids':[a,b]})
 assert r.status_code==200
 body=r.json()
 assert body['zone']=='冷藏'
 assert {c['field'] for c in body['conflicts']}=={'exposure','excursions','loss'}
def test_cross_zone_merge_rejected(client):
 s=TestSession();a=s.query(Sample).filter_by(code='S-A').first().id
 f=s.query(Sample).filter_by(code='S-F').first().id
 r=client.post('/identities/merge',headers=h(client),
  json={'request_id':rid('m',1),'sample_ids':[a,f],'choices':{}})
 assert r.status_code==409 and '跨温区' in r.json()['detail']
 assert s.query(MergeRequest).count()==0
def test_conflict_without_choice_rejected(client):
 s=TestSession();a=s.query(Sample).filter_by(code='S-A').first().id
 b=s.query(Sample).filter_by(code='S-B').first().id
 r=client.post('/identities/merge',headers=h(client),
  json={'request_id':rid('m',2),'sample_ids':[a,b],'choices':{}})
 assert r.status_code==409 and '冲突' in r.json()['detail']
def test_merge_corrects_old_records_and_recomputes_identity(client):
 s=TestSession()
 a=s.query(Sample).filter_by(code='S-A').first().id
 b=s.query(Sample).filter_by(code='S-B').first().id
 r=client.post('/identities/merge',headers=h(client),json={
  'request_id':rid('m',3),'sample_ids':[a,b],
  'choices':{'exposure':{'sample_id':b},'excursions':{'sample_id':a},'loss':{'sample_id':b}}})
 assert r.status_code==200,r.text
 body=r.json()
 assert body['corrections']==3
 s=TestSession()
 target=s.get(SampleIdentity,body['identity_id'])
 assert target.status=='merged' and target.version==2
 assert target.exposure==20 and target.excursions==1 and target.loss==3.0
 sa=s.query(Sample).filter_by(code='S-A').first()
 sb=s.query(Sample).filter_by(code='S-B').first()
 assert sa.exposure==20 and sa.excursions==1 and sa.loss==3.0
 assert sb.exposure==20 and sb.excursions==1 and sb.loss==3.0
 corrs=s.query(IdentityCorrection).all()
 assert len(corrs)==3
 pairs={(c.sample_id,c.field):(c.old_value,c.new_value,c.source) for c in corrs}
 assert pairs[(a,'exposure')]==(10,20.0,'S-B')
 assert pairs[(b,'excursions')]==(2,1,'S-A')
 members=s.query(IdentityMember).filter(IdentityMember.identity_id==target.id,IdentityMember.left_version.is_(None)).all()
 assert {m.sample_id for m in members}=={a,b}
 catalog=client.get('/identities',headers=h(client)).json()
 tcat=[i for i in catalog if i['id']==target.id][0]
 assert tcat['pair_count']==2
def test_merged_sample_cannot_be_edited_directly(client):
 s=TestSession()
 a=s.query(Sample).filter_by(code='S-A').first().id
 b=s.query(Sample).filter_by(code='S-B').first().id
 client.post('/identities/merge',headers=h(client),json={
  'request_id':rid('m',4),'sample_ids':[a,b],
  'choices':{'exposure':{'sample_id':b},'excursions':{'sample_id':a},'loss':{'sample_id':b}}})
 r=client.put(f'/samples/{a}',headers=h(client),
  json={'shipment_id':s.get(Sample,a).shipment_id,'code':'S-A','exposure':99,'excursions':1,'loss':2.0})
 assert r.status_code==409 and '拆回' in r.json()['detail']
def test_idempotent_retry_same_request_id(client):
 s=TestSession()
 a=s.query(Sample).filter_by(code='S-A').first().id
 b=s.query(Sample).filter_by(code='S-B').first().id
 payload={'request_id':rid('m',5),'sample_ids':[a,b],
  'choices':{'exposure':{'sample_id':b},'excursions':{'sample_id':a},'loss':{'sample_id':b}}}
 r1=client.post('/identities/merge',headers=h(client),json=payload)
 r2=client.post('/identities/merge',headers=h(client),json=payload)
 assert r1.json()==r2.json()
 s=TestSession()
 assert s.query(MergeRequest).count()==1
 assert s.query(IdentityCorrection).count()==3
def test_split_restores_separate_identities_keeps_corrections(client):
 s=TestSession()
 a=s.query(Sample).filter_by(code='S-A').first().id
 b=s.query(Sample).filter_by(code='S-B').first().id
 m=client.post('/identities/merge',headers=h(client),json={
  'request_id':rid('m',6),'sample_ids':[a,b],
  'choices':{'exposure':{'sample_id':b},'excursions':{'sample_id':a},'loss':{'sample_id':b}}}).json()
 r=client.post('/identities/split',headers=h(client),json={
  'request_id':rid('sp',1),'identity_id':m['identity_id'],'base_version':m['version'],'retain_sample_ids':[a]})
 assert r.status_code==200,r.text
 body=r.json()
 assert len(body['new_identity_ids'])==1
 s=TestSession()
 old=s.get(SampleIdentity,m['identity_id'])
 assert old.status=='split' and old.version==3
 new=s.get(SampleIdentity,body['new_identity_ids'][0])
 assert new.status=='unmerged' and new.display_code=='S-B'
 assert s.query(IdentityCorrection).count()==3
 sb=s.query(Sample).filter_by(code='S-B').first()
 assert sb.exposure==20
def test_split_rejects_stale_base_version(client):
 s=TestSession()
 a=s.query(Sample).filter_by(code='S-A').first().id
 b=s.query(Sample).filter_by(code='S-B').first().id
 m=client.post('/identities/merge',headers=h(client),json={
  'request_id':rid('m',7),'sample_ids':[a,b],
  'choices':{'exposure':{'sample_id':b},'excursions':{'sample_id':a},'loss':{'sample_id':b}}}).json()
 r=client.post('/identities/split',headers=h(client),json={
  'request_id':rid('sp',2),'identity_id':m['identity_id'],'base_version':99,'retain_sample_ids':[a]})
 assert r.status_code==409 and '过期' in r.json()['detail']
def test_split_idempotent_retry(client):
 s=TestSession()
 a=s.query(Sample).filter_by(code='S-A').first().id
 b=s.query(Sample).filter_by(code='S-B').first().id
 m=client.post('/identities/merge',headers=h(client),json={
  'request_id':rid('m',8),'sample_ids':[a,b],
  'choices':{'exposure':{'sample_id':b},'excursions':{'sample_id':a},'loss':{'sample_id':b}}}).json()
 payload={'request_id':rid('sp',3),'identity_id':m['identity_id'],'base_version':m['version'],'retain_sample_ids':[a]}
 r1=client.post('/identities/split',headers=h(client),json=payload)
 r2=client.post('/identities/split',headers=h(client),json=payload)
 assert r1.json()==r2.json()
 s=TestSession()
 assert s.query(SampleIdentity).count()==6
 assert s.query(MergeRequest).filter_by(kind='split').count()==1
def test_study_counts_each_identity_once_with_frozen_sources(client):
 s=TestSession()
 a=s.query(Sample).filter_by(code='S-A').first().id
 b=s.query(Sample).filter_by(code='S-B').first().id
 c=s.query(Sample).filter_by(code='S-C').first().id
 client.post('/identities/merge',headers=h(client),json={
  'request_id':rid('m',9),'sample_ids':[a,b],
  'choices':{'exposure':{'sample_id':b},'excursions':{'sample_id':a},'loss':{'sample_id':b}}})
 r=client.post('/studies',headers=h(client),
  json={'name':'冷藏暴露研究','zone':'冷藏','feature':'exposure'})
 assert r.status_code==200,r.text
 st_id=r.json()['id']
 s=TestSession()
 snap=s.get(Study,st_id).result['snapshot']
 assert len(snap)==3
 assert {row['display_code'] for row in snap}=={'S-A','S-C','S-D'}
 merged=[row for row in snap if row['display_code']=='S-A'][0]
 assert merged['pair_count']==2 and merged['exposure']==20
 assert set(merged['field_sources'])=={'exposure','excursions','loss'}
 from src.services.analysis import analyze
 with TestSession() as ws:
  row=ws.get(Study,st_id);snap=row.result['snapshot']
  row.result={**analyze(snap,row.feature),'snapshot':snap};row.state='done';ws.commit()
 s=TestSession()
 done=s.get(Study,st_id)
 assert done.state=='done' and done.result['n']==3
def test_identity_change_reopens_approved_recommendation(client):
 r=client.post('/studies',headers=h(client),
  json={'name':'冷藏研究2','zone':'冷藏','feature':'exposure'})
 assert r.status_code==200
 st_id=r.json()['id']
 with TestSession() as ws:
  row=ws.get(Study,st_id)
  row.state='done';row.result={'n':4,'excluded':0,'total':4,'pearson':0.5,'spearman':0.5,
   'pearson_p':0.1,'spearman_p':0.1,'points':[{'x':1,'y':2}],'version':'v1',
   'warning':'w','snapshot':row.result['snapshot']};ws.commit()
 rec=client.post('/recommendations',headers=h(client),
  json={'study_id':st_id,'note':'复核线路装卸等待时长并安排培训','owner':'王主管'}).json()
 appr=client.post(f'/recommendations/{rec["id"]}/approve',headers=h(client,'admin'))
 assert appr.status_code==200
 s=TestSession()
 a=s.query(Sample).filter_by(code='S-A').first().id
 b=s.query(Sample).filter_by(code='S-B').first().id
 m=client.post('/identities/merge',headers=h(client),json={
  'request_id':rid('m',10),'sample_ids':[a,b],
  'choices':{'exposure':{'sample_id':b},'excursions':{'sample_id':a},'loss':{'sample_id':b}}}).json()
 assert m['review_reopened']>=1
 s=TestSession()
 assert s.get(Recommendation,rec['id']).status=='review'
 r2=client.post(f'/recommendations/{rec["id"]}/approve',headers=h(client,'admin'))
 assert r2.status_code==409
def test_split_does_not_restore_approval(client):
 s=TestSession()
 a=s.query(Sample).filter_by(code='S-A').first().id
 b=s.query(Sample).filter_by(code='S-B').first().id
 st=client.post('/studies',headers=h(client),
  json={'name':'冷藏研究3','zone':'冷藏','feature':'exposure'}).json()
 with TestSession() as ws:
  row=ws.get(Study,st['id'])
  row.state='done';row.result={'n':4,'excluded':0,'total':4,'pearson':0.5,'spearman':0.5,
   'pearson_p':0.1,'spearman_p':0.1,'points':[{'x':1,'y':2}],'version':'v1','warning':'w',
   'snapshot':row.result['snapshot']};ws.commit()
 rec=client.post('/recommendations',headers=h(client),
  json={'study_id':st['id'],'note':'拆回不自动恢复签核的验收用例备注','owner':'李主管'}).json()
 client.post(f'/recommendations/{rec["id"]}/approve',headers=h(client,'admin'))
 m=client.post('/identities/merge',headers=h(client),json={
  'request_id':rid('m',11),'sample_ids':[a,b],
  'choices':{'exposure':{'sample_id':b},'excursions':{'sample_id':a},'loss':{'sample_id':b}}}).json()
 client.post('/identities/split',headers=h(client),json={
  'request_id':rid('sp',4),'identity_id':m['identity_id'],'base_version':m['version'],'retain_sample_ids':[a]})
 s=TestSession()
 assert s.get(Recommendation,rec['id']).status=='review'
def test_viewer_cannot_merge(client):
 s=TestSession();a=s.query(Sample).filter_by(code='S-A').first().id
 b=s.query(Sample).filter_by(code='S-B').first().id
 r=client.post('/identities/merge',headers=h(client,'viewer'),
  json={'request_id':rid('m',12),'sample_ids':[a,b],'choices':{}})
 assert r.status_code==403
def test_old_study_remains_readable_after_identity_change(client):
 r=client.post('/studies',headers=h(client),
  json={'name':'冻结快照研究','zone':'冷藏','feature':'exposure'})
 st_id=r.json()['id']
 with TestSession() as ws:
  row=ws.get(Study,st_id)
  snap=row.result['snapshot']
  row.state='done';row.result={'n':len(snap),'excluded':0,'total':len(snap),'pearson':0.5,
   'spearman':0.5,'pearson_p':0.1,'spearman_p':0.1,'points':[{'x':1,'y':2}],
   'version':'v1','warning':'w','snapshot':snap};ws.commit()
 before=client.get(f'/studies/{st_id}',headers=h(client)).json()
 s=TestSession();a=s.query(Sample).filter_by(code='S-A').first().id
 b=s.query(Sample).filter_by(code='S-B').first().id
 client.post('/identities/merge',headers=h(client),json={
  'request_id':rid('m',13),'sample_ids':[a,b],
  'choices':{'exposure':{'sample_id':b},'excursions':{'sample_id':a},'loss':{'sample_id':b}}})
 after=client.get(f'/studies/{st_id}',headers=h(client)).json()
 assert after['result']['snapshot']==before['result']['snapshot']
 assert len(after['result']['snapshot'])==4
def test_missing_field_not_in_sources_and_partial_conflict(client):
 s=TestSession()
 d=s.query(Sample).filter_by(code='S-D').first().id
 f=s.query(Sample).filter_by(code='S-F').first().id
 s.get(Sample,d).loss=None;s.commit()
 r=client.post('/identities/merge-preview',headers=h(client),json={
  'request_id':rid('pv',50),'sample_ids':[d,f]})
 assert r.status_code==409 and '跨温区' in r.json()['detail']
 a=s.query(Sample).filter_by(code='S-A').first().id
 r=client.post('/identities/merge-preview',headers=h(client),json={
  'request_id':rid('pv',51),'sample_ids':[a,d]})
 body=r.json()
 assert 'loss' not in {c['field'] for c in body['conflicts']}
 m=client.post('/identities/merge',headers=h(client),json={
  'request_id':rid('m',50),'sample_ids':[a,d],
  'choices':{'exposure':{'sample_id':d},'excursions':{'sample_id':d}}}).json()
 cat=[i for i in client.get('/identities',headers=h(client)).json() if i['id']==m['identity_id']][0]
 assert cat['field_sources'].get('loss')==a
 loss_fix=[c for c in cat['corrections'] if c['field']=='loss']
 assert len(loss_fix)==1 and loss_fix[0]['old_value'] is None
 sd=s.get(Sample,d)
 assert sd.loss==s.get(Sample,a).loss
def test_unmerged_sample_edit_syncs_identity(client):
 s=TestSession()
 c=s.query(Sample).filter_by(code='S-C').first().id
 ship=s.get(Sample,c).shipment_id
 r=client.put(f'/samples/{c}',headers=h(client),
  json={'shipment_id':ship,'code':'S-C','exposure':55,'excursions':4,'loss':7.2})
 assert r.status_code==200
 s=TestSession()
 ident=s.query(IdentityMember).filter_by(sample_id=c).first()
 row=s.get(SampleIdentity,ident.identity_id)
 assert row.status=='unmerged' and row.exposure==55 and row.excursions==4 and row.loss==7.2
def test_duplicate_member_in_request_rejected(client):
 s=TestSession()
 a=s.query(Sample).filter_by(code='S-A').first().id
 b=s.query(Sample).filter_by(code='S-B').first().id
 client.post('/identities/merge',headers=h(client),json={
  'request_id':rid('m',51),'sample_ids':[a,b],
  'choices':{'exposure':{'sample_id':b},'excursions':{'sample_id':a},'loss':{'sample_id':b}}})
 r=client.post('/identities/merge',headers=h(client),json={
  'request_id':rid('m',52),'sample_ids':[a,b],
  'choices':{'exposure':{'sample_id':b},'excursions':{'sample_id':a},'loss':{'sample_id':b}}})
 assert r.status_code==409 and '同组' in r.json()['detail']
def test_split_identity_not_mergable_again(client):
 s=TestSession()
 a=s.query(Sample).filter_by(code='S-A').first().id
 b=s.query(Sample).filter_by(code='S-B').first().id
 m=client.post('/identities/merge',headers=h(client),json={
  'request_id':rid('m',53),'sample_ids':[a,b],
  'choices':{'exposure':{'sample_id':b},'excursions':{'sample_id':a},'loss':{'sample_id':b}}}).json()
 client.post('/identities/split',headers=h(client),json={
  'request_id':rid('sp',50),'identity_id':m['identity_id'],'base_version':m['version'],'retain_sample_ids':[a]})
 r=client.post('/identities/merge',headers=h(client),json={
  'request_id':rid('m',54),'sample_ids':[a,b],'choices':{}})
 assert r.status_code==409
def test_stale_version_then_fresh_retry_applies_once(client):
 s=TestSession()
 a=s.query(Sample).filter_by(code='S-A').first().id
 b=s.query(Sample).filter_by(code='S-B').first().id
 m=client.post('/identities/merge',headers=h(client),json={
  'request_id':rid('m',55),'sample_ids':[a,b],
  'choices':{'exposure':{'sample_id':b},'excursions':{'sample_id':a},'loss':{'sample_id':b}}}).json()
 stale=client.post('/identities/split',headers=h(client),json={
  'request_id':rid('sp',51),'identity_id':m['identity_id'],'base_version':1,'retain_sample_ids':[a]})
 assert stale.status_code==409
 fresh=client.post('/identities/split',headers=h(client),json={
  'request_id':rid('sp',52),'identity_id':m['identity_id'],'base_version':m['version'],'retain_sample_ids':[a]})
 assert fresh.status_code==200
 s=TestSession()
 assert s.query(MergeRequest).filter_by(kind='split',status='applied').count()==1
def test_corrections_endpoint_lists_history(client):
 s=TestSession()
 a=s.query(Sample).filter_by(code='S-A').first().id
 b=s.query(Sample).filter_by(code='S-B').first().id
 m=client.post('/identities/merge',headers=h(client),json={
  'request_id':rid('m',56),'sample_ids':[a,b],
  'choices':{'exposure':{'sample_id':b},'excursions':{'sample_id':a},'loss':{'sample_id':b}}}).json()
 rows=client.get(f"/identities/{m['identity_id']}/corrections",headers=h(client)).json()
 assert len(rows)==3 and all(r['request_id']==rid('m',56) for r in rows)
 assert {'exposure','excursions','loss'}=={r['field'] for r in rows}
def test_merge_request_id_replay_returns_same_result(client):
 s=TestSession()
 a=s.query(Sample).filter_by(code='S-A').first().id
 b=s.query(Sample).filter_by(code='S-B').first().id
 payload={'request_id':rid('m',57),'sample_ids':[a,b],
  'choices':{'exposure':{'sample_id':b},'excursions':{'sample_id':a},'loss':{'sample_id':b}}}
 r1=client.post('/identities/merge',headers=h(client),json=payload)
 r2=client.post('/identities/merge',headers=h(client),json=payload)
 assert r1.json()==r2.json()
 s=TestSession()
 assert s.query(MergeRequest).count()==1
def test_merge_into_already_merged_identity(client):
 s=TestSession()
 a=s.query(Sample).filter_by(code='S-A').first().id
 b=s.query(Sample).filter_by(code='S-B').first().id
 d=s.query(Sample).filter_by(code='S-D').first().id
 m1=client.post('/identities/merge',headers=h(client),json={
  'request_id':rid('m',60),'sample_ids':[a,b],
  'choices':{'exposure':{'sample_id':b},'excursions':{'sample_id':a},'loss':{'sample_id':b}}}).json()
 r=client.post('/identities/merge',headers=h(client),json={
  'request_id':rid('m',61),'sample_ids':[a,d],
  'choices':{'exposure':{'sample_id':d},'excursions':{'sample_id':a},'loss':{'sample_id':d}}})
 assert r.status_code==200,r.text
 m2=r.json();assert m2['identity_id']==m1['identity_id'] and m2['version']==3
 s=TestSession()
 cat=client.get('/identities',headers=h(client)).json()
 target=[i for i in cat if i['id']==m1['identity_id']][0]
 assert set(target["active_sample_ids"])=={a,b,d} and target["pair_count"]==3
def test_edit_allowed_after_split_and_syncs_identity(client):
 s=TestSession()
 a=s.query(Sample).filter_by(code='S-A').first().id
 b=s.query(Sample).filter_by(code='S-B').first().id
 m=client.post('/identities/merge',headers=h(client),json={
  'request_id':rid('m',70),'sample_ids':[a,b],
  'choices':{'exposure':{'sample_id':b},'excursions':{'sample_id':a},'loss':{'sample_id':b}}}).json()
 client.post('/identities/split',headers=h(client),json={
  'request_id':rid('sp',70),'identity_id':m['identity_id'],'base_version':m['version'],'retain_sample_ids':[a]})
 ship=s.get(Sample,a).shipment_id
 r=client.put(f'/samples/{a}',headers=h(client),
  json={'shipment_id':ship,'code':'S-A','exposure':77,'excursions':6,'loss':8.8})
 assert r.status_code==200,r.text
 s=TestSession()
 mem=s.query(IdentityMember).filter(IdentityMember.sample_id==a,IdentityMember.left_version.is_(None)).first()
 row=s.get(SampleIdentity,mem.identity_id)
 assert row.exposure==77 and row.excursions==6 and row.loss==8.8
 assert row.field_sources=={'exposure':a,'excursions':a,'loss':a}
 s2=s.get(Sample,b)
 assert s2.exposure==20
