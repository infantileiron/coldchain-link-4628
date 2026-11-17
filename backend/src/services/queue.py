import os
import redis as _redis
def queue_study(study_id):
 client=_redis.Redis.from_url(os.environ['REDIS_URL'])
 client.rpush('studies',study_id)
def ping():
 _redis.Redis.from_url(os.environ['REDIS_URL']).ping()
