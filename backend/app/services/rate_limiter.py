import time
import redis
import logging

logger = logging.getLogger(__name__)

r = redis.Redis(host="redis", port=6379, decode_responses=True)

RPM_KEY        = "do_infer:rpm_limit"      # discovered ceiling (from headers)
REMAINING_KEY  = "do_infer:remaining"      # remaining in current window (from headers)
RESET_KEY      = "do_infer:reset_at"       # unix epoch when window resets (from headers)
WINDOW_KEY     = "do_infer:window"         # sliding-window request log

FALLBACK_RPM   = 10      # real observed DO serverless limit (~6-10 RPM effective)
SAFETY_FACTOR  = 0.85    # use 85% of the discovered ceiling for headroom


def acquire_slot():
    """Block until a request slot is free. Call immediately before every LLM request."""
    while True:
        now = time.time()
        
        # Determine the effective limit
        try:
            stored_limit = r.get(RPM_KEY)
            base_limit = float(stored_limit) if stored_limit else FALLBACK_RPM
        except Exception as e:
            logger.warning("Failed to read RPM_KEY from Redis: %s", e)
            base_limit = FALLBACK_RPM
            
        limit = int(base_limit * SAFETY_FACTOR)
        
        try:
            pipe = r.pipeline()
            pipe.zremrangebyscore(WINDOW_KEY, 0, now - 60)   # drop entries older than 60s
            pipe.zcard(WINDOW_KEY)
            _, count = pipe.execute()
            
            if count < limit:
                r.zadd(WINDOW_KEY, {f"{now}:{count}": now})
                r.expire(WINDOW_KEY, 60)
                return
                
            oldest = r.zrange(WINDOW_KEY, 0, 0, withscores=True)
            sleep_for = (oldest[0][1] + 60) - now if oldest else 1.0
            
        except Exception as e:
            logger.warning("Redis error in acquire_slot, failing open: %s", e)
            return  # Fail open if Redis is down
            
        time.sleep(max(sleep_for, 0.05))


def update_from_headers(headers):
    """Call after every response (success OR 429) to self-tune the limiter."""
    try:
        if "ratelimit-limit" in headers:
            r.set(RPM_KEY, int(headers["ratelimit-limit"]))
        if "ratelimit-remaining" in headers:
            r.set(REMAINING_KEY, int(headers["ratelimit-remaining"]))
        if "ratelimit-reset" in headers:
            r.set(RESET_KEY, float(headers["ratelimit-reset"]))
    except Exception as e:
        logger.warning("Failed to update rate limiter from headers: %s", e)
