"""Rate limits: 10 requests per customer per 60 seconds.

Both functions take the current time as an argument, so tests control the clock.

    allow_request_fixed(customer_id, now)    fixed window: one counter per calendar minute
    allow_request_sliding(customer_id, now)  sliding window: any 60 seconds, in a sorted set

Keys:
    ratelimit:fixed:{customer_id}:{minute}   string (INCR)  TTL 60 s
    ratelimit:sliding:{customer_id}          sorted set     TTL 60 s after the last accepted request
"""

import math
import os
import uuid

import redis

LIMIT = 10
WINDOW = 60  # seconds

r = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)


def allow_request_fixed(customer_id: int, now: float) -> bool:
    """The function of exercise 15, with the time as an argument."""
    key = f"ratelimit:fixed:{customer_id}:{int(now // WINDOW)}"
    pipe = r.pipeline(transaction=True)
    pipe.incr(key)
    pipe.expire(key, WINDOW, nx=True)
    count, _ = pipe.execute()
    return count <= LIMIT


# Remove the requests older than the window, count what is left, and record this
# request only if it is allowed: all in one script, so no other command can run
# between the count and the add.
SLIDING = r.register_script("""
local key    = KEYS[1]
local now    = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit  = tonumber(ARGV[3])
local member = ARGV[4]

redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
if redis.call('ZCARD', key) >= limit then
    return 0
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, math.ceil(window))
return 1
""")


def sliding_key(customer_id: int) -> str:
    return f"ratelimit:sliding:{customer_id}"


def allow_request_sliding(customer_id: int, now: float) -> bool:
    # The member must be unique: two requests at the same time would otherwise be the
    # same member, and the second ZADD would only update the first one's score.
    member = f"{now:.6f}:{uuid.uuid4().hex}"
    return SLIDING(keys=[sliding_key(customer_id)], args=[now, WINDOW, LIMIT, member]) == 1


def allow_request_sliding_not_atomic(customer_id: int, now: float, between=None) -> bool:
    """The same logic in separate commands, ONLY to show why it must be atomic.

    `between` is called between the count and the add, where another client can run.
    """
    key = sliding_key(customer_id)
    r.zremrangebyscore(key, "-inf", now - WINDOW)
    count = r.zcard(key)
    if between:
        between()
    if count >= LIMIT:
        return False
    r.zadd(key, {f"{now:.6f}:{uuid.uuid4().hex}": now})
    r.expire(key, math.ceil(WINDOW))
    return True
