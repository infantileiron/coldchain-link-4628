from fastapi import HTTPException
from sqlalchemy.exc import OperationalError
from src.models.entities import Shipment,Sample,SampleIdentity,IdentityMember,Study
from src.services.identity import study_snapshot,ensure_unmerged_identity
def ensure_shipment(s,i):
 if not s.get(Shipment,i):raise HTTPException(404,'班次不存在')
def study_rows(s,zone):
 return study_snapshot(s,zone)
def ensure_study(s,i):
 row=s.get(Study,i)
 if not row:raise HTTPException(404,'研究不存在')
 return row
def ensure_sample(s,i):
 row=s.get(Sample,i)
 if not row:raise HTTPException(404,'样本不存在')
 return row
def ensure_identity_for_sample(s,sample):
 member=s.query(IdentityMember).filter_by(sample_id=sample.id).first()
 if not member:return ensure_unmerged_identity(s,sample)
 ident=s.get(SampleIdentity,member.identity_id)
 if ident.status in ('pending','merged'):
  raise HTTPException(409,'样本已归入合并身份，请先拆回后再直接修改原记录')
 return ident
def lock_sample(s,sample_id):
 try:
  return s.query(Sample).filter(Sample.id==sample_id).with_for_update().one_or_none()
 except OperationalError:s.rollback();raise HTTPException(409,'记录正被归并操作占用，请稍后重试')
