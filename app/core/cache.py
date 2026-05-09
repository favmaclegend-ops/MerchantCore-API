from cachetools import TTLCache

user_cache: TTLCache = TTLCache(maxsize=1024, ttl=60)
user_list_cache: TTLCache = TTLCache(maxsize=1, ttl=30)
