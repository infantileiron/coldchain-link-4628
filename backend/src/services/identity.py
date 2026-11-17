from datetime import datetime,timezone
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError,OperationalError
from src.models.entities import Audit,Shipment,Sample,SampleIdentity,IdentityMember,IdentityCorrection,MergeRequest,Study,Recommendation
from src.constants.enums import MEASURE_FIELDS
def now_iso():return datetime.now(timezone.utc).isoformat()
def audit(s,u,action):
 s.add(Audit(actor=u.email,action=action,created=now_iso()));s.commit()
def dump(obj):return {c.name:getattr(obj,c.name) for c in obj.__table__.columns if c.name!='password'}
def _lock_identities(s,ids):
 rows=[]
 for i in sorted(set(ids)):
  q=s.query(SampleIdentity).filter(SampleIdentity.id==i)
  try:row=q.with_for_update().one_or_none()
  except OperationalError:raise
  rows.append(row)
 return rows
def ensure_unmerged_identity(s,sample):
 existing=s.query(IdentityMember).filter_by(sample_id=sample.id).first()
 if existing:return s.get(SampleIdentity,existing.identity_id)
 ts=now_iso()
 ident=SampleIdentity(status='unmerged',version=1,zone=None,
  display_code=sample.code,exposure=sample.exposure,excursions=sample.excursions,loss=sample.loss,
  field_sources={f:sample.id for f in MEASURE_FIELDS if getattr(sample,f) is not None},
  created=ts,updated=ts)
 s.add(ident);s.flush()
 s.add(IdentityMember(identity_id=ident.id,sample_id=sample.id,sample_code=sample.code,joined_version=1))
 return ident
def provision_identities(s):
 known={m.sample_id for m in s.query(IdentityMember).all()}
 q=s.query(Sample)
 missing=q.filter(~Sample.id.in_(known)).all() if known else q.all()
 for sp in missing:
  ship=s.get(Shipment,sp.shipment_id)
  ident=ensure_unmerged_identity(s,sp)
  if ship:ident.zone=ship.zone
 return len(missing)
def _identity_samples(s,ident_id):
 return (s.query(Sample,IdentityMember)
  .join(IdentityMember,IdentityMember.sample_id==Sample.id)
  .filter(IdentityMember.identity_id==ident_id,IdentityMember.left_version.is_(None)).all())
def merge_preview(s,sample_ids):
 provision_identities(s)
 idents=s.query(IdentityMember).filter(IdentityMember.sample_id.in_(sample_ids),
  IdentityMember.left_version.is_(None)).all()
 ident_by_sample={m.sample_id:m.identity_id for m in idents}
 ident_ids=sorted(set(ident_by_sample.values()))
 if len(ident_by_sample)!=len(sample_ids) or len(ident_ids)!=len(sample_ids):
  raise HTTPException(409,'存在已同组样本，请检查配对清单')
 rows=s.query(SampleIdentity).filter(SampleIdentity.id.in_(ident_ids)).all()
 if any(r.status in ('pending','split') for r in rows):
  raise HTTPException(409,'待核对或已拆回的身份不能再次归并')
 zones={r.zone for r in rows}
 if len(zones)>1:
  raise HTTPException(409,f'跨温区拒绝合并：{ "、".join(sorted(z for z in zones if z)) }')
 samples=s.query(Sample).filter(Sample.id.in_(sample_ids)).all()
 sample_map={sp.id:sp for sp in samples}
 conflicts=[]
 for f in MEASURE_FIELDS:
  vals={}
  for sp in samples:
   v=getattr(sp,f)
   if v is not None:vals.setdefault(v,[]).append(sp.id)
  if len(vals)>1:
   conflicts.append({'field':f,'values':[{'value':v,'sample_ids':ids} for v,ids in vals.items()]})
 return {'zone':next(iter(zones),None),'identity_ids':ident_ids,'conflicts':conflicts,
  'samples':[dump(sp) for sp in samples]}
def _reopen_reviews(s,ident_ids,actor):
 touched=set()
 for st in s.query(Study).all():
  snap=(st.result or {}).get('snapshot') or []
  if any(row.get('identity_id') in ident_ids for row in snap):touched.add(st.id)
 if not touched:return 0
 n=0
 for rec in s.query(Recommendation).filter(Recommendation.study_id.in_(touched),Recommendation.status=='approved').all():
  rec.status='review';n+=1
  s.add(Audit(actor=actor,action=f'身份变化，建议 {rec.id} 转待复核',created=now_iso()))
 return n
def merge_identities(s,user,data):
 prior=s.query(MergeRequest).filter_by(request_id=data.request_id).first()
 if prior:return prior.response
 provision_identities(s)
 sample_ids=sorted(set(data.sample_ids))
 if len(sample_ids)<2:raise HTTPException(422,'至少选择两条样本')
 member_rows=s.query(IdentityMember).filter(IdentityMember.sample_id.in_(sample_ids),
  IdentityMember.left_version.is_(None)).all()
 ident_by_sample={m.sample_id:m.identity_id for m in member_rows}
 if set(ident_by_sample)!=set(sample_ids):
  raise HTTPException(404,'部分样本尚无身份档案')
 ident_ids=sorted(set(ident_by_sample.values()))
 if len(ident_ids)!=len(sample_ids):
  raise HTTPException(409,'存在已同组样本，无需重复归并')
 try:rows=_lock_identities(s,ident_ids)
 except OperationalError:s.rollback();raise HTTPException(409,'归并冲突，请刷新后重试')
 if any(r is None for r in rows):
  s.rollback();raise HTTPException(404,'身份档案缺失')
 prior=s.query(MergeRequest).filter_by(request_id=data.request_id).first()
 if prior:return prior.response
 by_id={r.id:r for r in rows}
 if any(r.status in ('pending','split') for r in rows):
  s.rollback();raise HTTPException(409,'待核对或已拆回的身份不能再次归并')
 zones={r.zone for r in rows if r.zone}
 if len(zones)>1:
  s.rollback();raise HTTPException(409,f'跨温区拒绝合并：{ "、".join(sorted(zones)) }')
 pairs=s.query(Sample,IdentityMember).join(IdentityMember,IdentityMember.sample_id==Sample.id)\
  .filter(IdentityMember.identity_id.in_(ident_ids),IdentityMember.left_version.is_(None)).all()
 sample_map={sp.id:sp for sp,_ in pairs}
 group_ident={sp.id:mem.identity_id for sp,mem in pairs}
 if not set(sample_ids).issubset(sample_map):
  s.rollback();raise HTTPException(409,'成员状态已变化，请刷新后重试')
 chosen={}
 for f in MEASURE_FIELDS:
  present={group_ident[sid]:getattr(sp,f) for sid,sp in sample_map.items() if getattr(sp,f) is not None}
  distinct=set(present.values())
  if len(distinct)>1:
   pick=data.choices.get(f)
   if not pick:
    s.rollback();raise HTTPException(409,f'字段 {f} 存在冲突值，必须逐项选择来源')
   src_ident=group_ident.get(pick.sample_id)
   if src_ident not in present:
    s.rollback();raise HTTPException(409,f'字段 {f} 的来源样本无效或该字段为空')
   chosen[f]=(present[src_ident],pick.sample_id)
  elif present:
   src_ident=next(iter(present));chosen[f]=(present[src_ident],next(sid for sid,iid in group_ident.items() if iid==src_ident))
 target_id=min(ident_ids);target=by_id[target_id]
 ts=now_iso()
 corrections=0
 for sid,sp in sample_map.items():
  for f,(new_value,src_sid) in chosen.items():
   old_value=getattr(sp,f)
   if old_value!=new_value:
    setattr(sp,f,new_value)
    s.add(IdentityCorrection(identity_id=target_id,sample_id=sid,field=f,old_value=old_value,
     new_value=new_value,source=sample_map[src_sid].code,request_id=data.request_id,
     version=target.version+1,created=ts));corrections+=1
 for f,(new_value,src_sid) in chosen.items():setattr(target,f,new_value)
 target.field_sources={f:sample_map[src_sid].id for f,(new_value,src_sid) in chosen.items()}
 target.status='merged';target.version+=1;target.updated=ts
 target.display_code=sample_map[next(sid for sid,iid in group_ident.items() if iid==target_id)].code
 for r in rows:
  if r.id!=target_id:
   r.status='merged';r.version+=1;r.updated=ts
 for m in s.query(IdentityMember).filter(IdentityMember.identity_id.in_(ident_ids),
   IdentityMember.identity_id!=target_id,IdentityMember.left_version.is_(None)).all():
  m.left_version=target.version
  s.add(IdentityMember(identity_id=target_id,sample_id=m.sample_id,sample_code=m.sample_code,joined_version=target.version))
 reviews=_reopen_reviews(s,ident_ids,user.email)
 resp={'identity_id':target_id,'version':target.version,'corrections':corrections,
  'review_reopened':reviews,'field_sources':target.field_sources}
 s.add(MergeRequest(request_id=data.request_id,kind='merge',identity_id=target_id,
  base_version=target.version-1,status='applied',response=resp,actor=user.email,created=ts))
 try:s.commit()
 except IntegrityError:s.rollback();raise HTTPException(409,'请求编号重复或数据已变化，请刷新后重试')
 audit(s,user,f'归并样本身份 {target_id}（{len(sample_ids)} 条，更正 {corrections} 项）')
 return resp
def split_identity(s,user,data):
 prior=s.query(MergeRequest).filter_by(request_id=data.request_id).first()
 if prior:return prior.response
 try:row=s.query(SampleIdentity).filter(SampleIdentity.id==data.identity_id).with_for_update().one_or_none()
 except OperationalError:s.rollback();raise HTTPException(409,'拆回冲突，请刷新后重试')
 if not row:raise HTTPException(404,'身份不存在')
 if row.status!='merged':s.rollback();raise HTTPException(409,'仅已合并身份可以拆回')
 if row.version!=data.base_version:s.rollback();raise HTTPException(409,'方案已过期：身份版本已变化，请刷新后重试')
 prior=s.query(MergeRequest).filter_by(request_id=data.request_id).first()
 if prior:return prior.response
 pairs=_identity_samples(s,row.id)
 if not pairs:s.rollback();raise HTTPException(409,'身份没有在组成员')
 retain=set(data.retain_sample_ids)
 member_ids={sp.id for sp,_ in pairs}
 if not retain or not retain.issubset(member_ids):
  s.rollback();raise HTTPException(404,'保留样本不属于该身份')
 ts=now_iso();new_ids=[]
 for sp,mem in pairs:
  if sp.id in retain:continue
  ident=SampleIdentity(status='unmerged',version=1,zone=row.zone,display_code=sp.code,
   exposure=sp.exposure,excursions=sp.excursions,loss=sp.loss,
   field_sources={f:sp.id for f in MEASURE_FIELDS if getattr(sp,f) is not None},
   created=ts,updated=ts)
  s.add(ident);s.flush();new_ids.append(ident.id)
  mem.left_version=row.version+1
  s.add(IdentityMember(identity_id=ident.id,sample_id=sp.id,sample_code=sp.code,joined_version=1))
 kept=[sp for sp,_ in pairs if sp.id in retain]
 if kept:row.display_code=kept[0].code
 row.status='split';row.version+=1;row.updated=ts
 reviews=_reopen_reviews(s,[row.id]+new_ids,user.email)
 resp={'identity_id':row.id,'new_identity_ids':new_ids,'version':row.version,
  'retained':sorted(retain),'review_reopened':reviews,
  'note':'拆回不自动恢复签核；合并期间的更正已原样保留'}
 s.add(MergeRequest(request_id=data.request_id,kind='split',identity_id=row.id,
  base_version=data.base_version,status='applied',response=resp,actor=user.email,created=ts))
 try:s.commit()
 except IntegrityError:s.rollback();raise HTTPException(409,'请求编号重复或数据已变化，请刷新后重试')
 audit(s,user,f'拆回身份 {row.id}（新身份 {len(new_ids)} 个，更正保留）')
 return resp
def identity_catalog(s):
 provision_identities(s)
 out=[]
 for ident in s.query(SampleIdentity).order_by(SampleIdentity.id).all():
  members=(s.query(IdentityMember).filter_by(identity_id=ident.id)
   .order_by(IdentityMember.id).all())
  active=[m for m in members if m.left_version is None]
  corrections=s.query(IdentityCorrection).filter_by(identity_id=ident.id).order_by(IdentityCorrection.id).all()
  out.append({**dump(ident),'pair_count':len(active),
   'members':[dump(m) for m in members],
   'active_sample_ids':[m.sample_id for m in active],
   'corrections':[dump(c) for c in corrections]})
 return out
def study_snapshot(s,zone):
 provision_identities(s)
 rows=(s.query(Sample,Shipment).join(Shipment,Shipment.id==Sample.shipment_id)
  .filter(Shipment.zone==zone).all())
 members=s.query(IdentityMember).filter(IdentityMember.left_version.is_(None)).all()
 current={m.sample_id:m.identity_id for m in members}
 ident_cache={i.id:i for i in s.query(SampleIdentity).all()}
 per_ident={}
 for sp,ship in rows:
  iid=current.get(sp.id)
  if iid is None:continue
  per_ident.setdefault(iid,[]).append(sp)
 snapshot=[]
 for iid,group in per_ident.items():
  ident=ident_cache[iid]
  snapshot.append({'identity_id':iid,'display_code':ident.display_code,
   'pair_count':len(group),'sample_codes':[sp.code for sp in group],
   'exposure':ident.exposure,'excursions':ident.excursions,'loss':ident.loss,
   'field_sources':dict(ident.field_sources or {}),'zone':zone})
 return snapshot
