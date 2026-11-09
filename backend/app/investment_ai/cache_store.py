"""Shared Redis L2 cache and cross-pod run coordinator with thread-safe in-memory fallback.

In Kubernetes, ``backend`` runs multiple replicas alongside a shared ``redis`` service.
When Redis is reachable, cached market/screener/fundamental payloads and ``/api/swarm/stop``
signals are shared across all pods. When Redis is unreachable (e.g. local dev or unit tests),
all helpers fall back transparently to fast in-memory structures without raising errors.
"""

import copy
import json
import logging
import threading
import time
from typing import Any, Dict, Optional, Tuple

from app.config import settings

logger = logging.getLogger(__name__)

_REDIS_RETRY_COOLDOWN = 30.0
_redis_lock = threading.Lock()
_redis_client: Any = None
_redis_retry_after: float = 0.0

_mem_lock = threading.Lock()
_mem_cache: Dict[str, Tuple[float, Any]] = {}
_MAX_MEM_ENTRIES = 4096

_runs_lock = threading.Lock()
_local_runs: Dict[str, threading.Event] = {}


def _get_redis() -> Any:
    """Returns a live Redis client, or None if Redis is unavailable or cooling down."""
    global _redis_client, _redis_retry_after

    now = time.monotonic()
    if now < _redis_retry_after:
        return None

    client = _redis_client
    if client is not None:
        return client

    with _redis_lock:
        now = time.monotonic()
        if now < _redis_retry_after:
            return None
        if _redis_client is not None:
            return _redis_client

        redis_url = (getattr(settings, "REDIS_URL", "") or "").strip()
        if not redis_url:
            _redis_retry_after = now + _REDIS_RETRY_COOLDOWN
            return None

        try:
            import redis  # type: ignore[import-untyped]

            candidate = redis.Redis.from_url(
                redis_url,
                socket_connect_timeout=0.4,
                socket_timeout=0.5,
                decode_responses=True,
                health_check_interval=30,
            )
            candidate.ping()
            _redis_client = candidate
            logger.info("Connected to shared Redis store for cross-pod caching & run control")
            return _redis_client
        except Exception as e:
            logger.debug("Redis unavailable (%s); using in-process fallback for %.0fs", e, _REDIS_RETRY_COOLDOWN)
            _redis_client = None
            _redis_retry_after = now + _REDIS_RETRY_COOLDOWN
            return None


def _mark_redis_failed(err: Exception) -> None:
    global _redis_client, _redis_retry_after
    with _redis_lock:
        _redis_client = None
        _redis_retry_after = time.monotonic() + _REDIS_RETRY_COOLDOWN
    logger.debug("Redis operation failed (%s); falling back to memory temporarily", err)


def redis_get_json(key: str) -> Tuple[bool, Any]:
    """Reads a JSON-serialized value from Redis only (used as L2 behind existing L1 caches)."""
    client = _get_redis()
    if client is None:
        return False, None
    try:
        raw = client.get(f"ata:v1:{key}")
        if raw is None:
            return False, None
        return True, json.loads(raw)
    except Exception as e:
        _mark_redis_failed(e)
        return False, None


def redis_set_json(key: str, value: Any, ttl_seconds: float) -> bool:
    """Writes a JSON-serializable value to Redis with a positive TTL."""
    ttl = max(1, int(round(ttl_seconds)))
    client = _get_redis()
    if client is None:
        return False
    try:
        payload = json.dumps(value, ensure_ascii=False)
        client.setex(f"ata:v1:{key}", ttl, payload)
        return True
    except Exception as e:
        _mark_redis_failed(e)
        return False


def shared_cache_get(key: str) -> Tuple[bool, Any]:
    """Reads from process-local L1 memory first, then shared Redis L2."""
    now = time.monotonic()
    with _mem_lock:
        hit = _mem_cache.get(key)
        if hit is not None:
            expires_at, val = hit
            if now < expires_at:
                return True, copy.deepcopy(val)
            _mem_cache.pop(key, None)

    found, val = redis_get_json(key)
    if found:
        with _mem_lock:
            _mem_cache[key] = (now + 30.0, copy.deepcopy(val))
        return True, val
    return False, None


def shared_cache_set(
    key: str,
    value: Any,
    ttl_seconds: float,
    *,
    l1_ttl_seconds: Optional[float] = None,
) -> None:
    """Stores a value in both L1 process memory and L2 Redis."""
    if ttl_seconds <= 0:
        return
    effective_l1 = ttl_seconds if l1_ttl_seconds is None else min(ttl_seconds, l1_ttl_seconds)
    expires_at = time.monotonic() + effective_l1
    with _mem_lock:
        if len(_mem_cache) >= _MAX_MEM_ENTRIES:
            now = time.monotonic()
            expired = [k for k, (exp, _) in _mem_cache.items() if now >= exp]
            for k in expired:
                _mem_cache.pop(k, None)
            if len(_mem_cache) >= _MAX_MEM_ENTRIES:
                _mem_cache.clear()
        _mem_cache[key] = (expires_at, copy.deepcopy(value))
    redis_set_json(key, value, ttl_seconds)


def shared_cache_delete(key: str) -> None:
    with _mem_lock:
        _mem_cache.pop(key, None)
    client = _get_redis()
    if client is not None:
        try:
            client.delete(f"ata:v1:{key}")
        except Exception as e:
            _mark_redis_failed(e)


def shared_cache_clear() -> None:
    """Clears L1 memory entries (useful in unit tests)."""
    with _mem_lock:
        _mem_cache.clear()


# ---------------------------------------------------------------------------
# Cross-pod Swarm Run Registry & Stop Signal Coordination
# ---------------------------------------------------------------------------


def register_run(run_id: str, stop_event: threading.Event, ttl_seconds: int = 900) -> None:
    """Registers an active swarm run locally and in Redis so any pod can stop it."""
    if not run_id:
        return
    with _runs_lock:
        _local_runs[run_id] = stop_event

    client = _get_redis()
    if client is not None:
        try:
            client.setex(f"ata:v1:swarm:run:{run_id}", max(60, ttl_seconds), "active")
        except Exception as e:
            _mark_redis_failed(e)


def request_stop_run(run_id: str, ttl_seconds: int = 300) -> bool:
    """Signals a running swarm pipeline to stop, across both local pod and Redis."""
    if not run_id:
        return False

    found_local = False
    with _runs_lock:
        ev = _local_runs.get(run_id)
        if ev is not None:
            ev.set()
            found_local = True

    found_remote = False
    client = _get_redis()
    if client is not None:
        try:
            run_key = f"ata:v1:swarm:run:{run_id}"
            stop_key = f"ata:v1:swarm:stop:{run_id}"
            if client.exists(run_key):
                found_remote = True
            # Always write the stop marker with a short TTL in case stop arrives slightly
            # before or alongside stream registration on another replica.
            if found_local or found_remote:
                client.setex(stop_key, max(30, ttl_seconds), "1")
        except Exception as e:
            _mark_redis_failed(e)

    return found_local or found_remote


def sync_stop_event(run_id: str, stop_event: Optional[threading.Event]) -> bool:
    """Checks Redis for a cross-pod stop request and sets ``stop_event`` if found."""
    if stop_event is None:
        return False
    if stop_event.is_set():
        return True
    if not run_id:
        return False

    client = _get_redis()
    if client is None:
        return stop_event.is_set()
    try:
        if client.get(f"ata:v1:swarm:stop:{run_id}"):
            stop_event.set()
            return True
    except Exception as e:
        _mark_redis_failed(e)
    return stop_event.is_set()


def cleanup_run(run_id: str) -> None:
    """Removes a completed/aborted run from local memory and Redis."""
    if not run_id:
        return
    with _runs_lock:
        _local_runs.pop(run_id, None)

    client = _get_redis()
    if client is not None:
        try:
            client.delete(f"ata:v1:swarm:run:{run_id}", f"ata:v1:swarm:stop:{run_id}")
        except Exception as e:
            _mark_redis_failed(e)

