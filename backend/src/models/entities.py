from sqlalchemy import Column,Integer,String,Float,JSON,Text,Computed
from src.config.database import Base
class User(Base):
 __tablename__='users'
 id=Column(Integer,primary_key=True);email=Column(String(100),unique=True);password=Column(String(200));role=Column(String(20))
class Shipment(Base):
 __tablename__='shipments'
 id=Column(Integer,primary_key=True);code=Column(String(60),unique=True);route=Column(String(60));zone=Column(String(20));driver=Column(String(60))
class Sample(Base):
 __tablename__='samples'
 id=Column(Integer,primary_key=True);shipment_id=Column(Integer,index=True);code=Column(String(60),unique=True);exposure=Column(Float,nullable=True);excursions=Column(Integer,nullable=True);loss=Column(Float,nullable=True)
class Study(Base):
 __tablename__='studies'
 id=Column(Integer,primary_key=True);name=Column(String(100));zone=Column(String(20));feature=Column(String(30));state=Column(String(20),default='queued');result=Column(JSON,nullable=True);error=Column(Text,default='')
class Recommendation(Base):
 __tablename__='recommendations'
 id=Column(Integer,primary_key=True);study_id=Column(Integer);note=Column(Text);owner=Column(String(60));status=Column(String(20),default='draft')
class Audit(Base):
 __tablename__='audits'
 id=Column(Integer,primary_key=True);actor=Column(String(100));action=Column(String(200));created=Column(String(40))
class SampleIdentity(Base):
 __tablename__='sample_identities'
 id=Column(Integer,primary_key=True)
 status=Column(String(20),default='unmerged',index=True)
 version=Column(Integer,default=1,nullable=False)
 zone=Column(String(20),nullable=True)
 display_code=Column(String(60))
 exposure=Column(Float,nullable=True)
 excursions=Column(Integer,nullable=True)
 loss=Column(Float,nullable=True)
 field_sources=Column(JSON,default=dict)
 created=Column(String(40));updated=Column(String(40))
class IdentityMember(Base):
 __tablename__='identity_members'
 id=Column(Integer,primary_key=True)
 identity_id=Column(Integer,index=True)
 sample_id=Column(Integer,index=True)
 sample_code=Column(String(60))
 joined_version=Column(Integer,default=1)
 left_version=Column(Integer,nullable=True)
 active_sample_id=Column(Integer,Computed('CASE WHEN left_version IS NULL THEN sample_id ELSE NULL END'),unique=True)
class IdentityCorrection(Base):
 __tablename__='identity_corrections'
 id=Column(Integer,primary_key=True)
 identity_id=Column(Integer,index=True)
 sample_id=Column(Integer)
 field=Column(String(20))
 old_value=Column(Float,nullable=True)
 new_value=Column(Float,nullable=True)
 source=Column(String(20))
 request_id=Column(String(60),index=True)
 version=Column(Integer)
 created=Column(String(40))
class MergeRequest(Base):
 __tablename__='merge_requests'
 id=Column(Integer,primary_key=True)
 request_id=Column(String(60),unique=True,index=True)
 kind=Column(String(20))
 identity_id=Column(Integer,index=True)
 base_version=Column(Integer)
 status=Column(String(20),default='applied')
 response=Column(JSON,nullable=True)
 actor=Column(String(100))
 created=Column(String(40))
