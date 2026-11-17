from pydantic import BaseModel,Field
from typing import Optional,Literal
class Login(BaseModel):
 email:str;password:str
class ShipmentInput(BaseModel):
 code:str=Field(min_length=1,max_length=60);route:str=Field(min_length=1,max_length=60);zone:Literal['冷藏','冷冻','常温对照'];driver:str=Field(min_length=1,max_length=60)
class SampleInput(BaseModel):
 shipment_id:int;code:str=Field(min_length=1,max_length=60);exposure:Optional[float]=Field(default=None,ge=0,le=1440);excursions:Optional[int]=Field(default=None,ge=0,le=100);loss:Optional[float]=Field(default=None,ge=0,le=100)
class StudyInput(BaseModel):
 name:str=Field(min_length=1,max_length=100);zone:Literal['冷藏','冷冻','常温对照'];feature:Literal['exposure','excursions']='exposure'
class RecommendationInput(BaseModel):
 study_id:int;note:str=Field(min_length=10,max_length=2000);owner:str=Field(min_length=1,max_length=60)
class MergeChoice(BaseModel):
 sample_id:int
class MergeInput(BaseModel):
 request_id:str=Field(min_length=8,max_length=60)
 sample_ids:list[int]=Field(min_length=2)
 choices:dict[str,MergeChoice]={}
class SplitInput(BaseModel):
 request_id:str=Field(min_length=8,max_length=60)
 identity_id:int
 base_version:int
 retain_sample_ids:list[int]=Field(min_length=1)
