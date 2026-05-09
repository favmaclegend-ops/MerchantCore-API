from cachetools import TTLCache

user_cache: TTLCache = TTLCache(maxsize=1024, ttl=60)
user_list_cache: TTLCache = TTLCache(maxsize=1, ttl=30)
product_cache: TTLCache = TTLCache(maxsize=256, ttl=60)
product_list_cache: TTLCache = TTLCache(maxsize=1, ttl=30)
customer_cache: TTLCache = TTLCache(maxsize=256, ttl=60)
customer_list_cache: TTLCache = TTLCache(maxsize=1, ttl=30)
transaction_list_cache: TTLCache = TTLCache(maxsize=1, ttl=30)
credit_list_cache: TTLCache = TTLCache(maxsize=1, ttl=30)
sale_list_cache: TTLCache = TTLCache(maxsize=1, ttl=30)
