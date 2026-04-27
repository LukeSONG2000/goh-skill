"""File-based JSON cache with TTL for SWGOH data."""

import json
import os
import time
from datetime import datetime, timezone
from typing import Optional, Union, Dict, List

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache")

# Default TTL in seconds per cache key
DEFAULT_TTLS = {
    "characters": 86400,    # 24h
    "abilities": 86400,     # 24h
    "ships": 86400,         # 24h
    "gear": 86400,          # 24h
    "gac-config": 3600,     # 1h
    "gac-battles": 3600,    # 1h
    "gac-squads": 3600,     # 1h
    "gac-leaders": 3600,    # 1h
    "cf-session": 1500,     # 25m
}

# Mods have their own subdirectory, TTL 12h
MODS_TTL = 43200


def _ensure_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(os.path.join(CACHE_DIR, "mods"), exist_ok=True)


def _cache_path(key: str) -> str:
    if key.startswith("mods/"):
        return os.path.join(CACHE_DIR, f"{key}.json")
    return os.path.join(CACHE_DIR, f"{key}.json")


def get(key: str, ttl: Optional[int] = None) -> Optional[Union[list, dict]]:
    """Get cached data if still fresh. Returns None if missing or stale."""
    _ensure_dir()
    path = _cache_path(key)
    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            entry = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    fetched_at = entry.get("fetched_at", 0)
    effective_ttl = ttl if ttl is not None else DEFAULT_TTLS.get(key, MODS_TTL if key.startswith("mods/") else 3600)

    if time.time() - fetched_at > effective_ttl:
        return None

    return entry.get("data")


def set(key: str, data) -> None:
    """Write data to cache with current timestamp."""
    _ensure_dir()
    path = _cache_path(key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    entry = {
        "fetched_at": time.time(),
        "fetched_at_iso": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False)


def clear(key: Optional[str] = None) -> List[str]:
    """Clear cache. If key is None, clear all. Returns list of cleared keys."""
    _ensure_dir()
    cleared = []

    if key is None:
        for fname in os.listdir(CACHE_DIR):
            fpath = os.path.join(CACHE_DIR, fname)
            if fname.endswith(".json") and os.path.isfile(fpath):
                os.remove(fpath)
                cleared.append(fname.replace(".json", ""))
        # Clear mods subdir too
        mods_dir = os.path.join(CACHE_DIR, "mods")
        if os.path.isdir(mods_dir):
            for fname in os.listdir(mods_dir):
                fpath = os.path.join(mods_dir, fname)
                if fname.endswith(".json") and os.path.isfile(fpath):
                    os.remove(fpath)
                    cleared.append(f"mods/{fname.replace('.json', '')}")
    else:
        path = _cache_path(key)
        if os.path.exists(path):
            os.remove(path)
            cleared.append(key)

    return cleared


def status() -> Dict:
    """Return freshness status for all cached items."""
    _ensure_dir()
    result = {}

    for fname in sorted(os.listdir(CACHE_DIR)):
        if not fname.endswith(".json"):
            continue
        key = fname.replace(".json", "")
        path = os.path.join(CACHE_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                entry = json.load(f)
            fetched_at = entry.get("fetched_at", 0)
            fetched_iso = entry.get("fetched_at_iso", "?")
            ttl = DEFAULT_TTLS.get(key, MODS_TTL if key.startswith("mods/") else 3600)
            age = int(time.time() - fetched_at)
            fresh = age < ttl
            size = os.path.getsize(path)
            result[key] = {
                "fetched_at": fetched_iso,
                "age_seconds": age,
                "ttl_seconds": ttl,
                "fresh": fresh,
                "size_bytes": size,
            }
        except (json.JSONDecodeError, OSError):
            result[key] = {"fresh": False, "error": True}

    # Check mods subdir
    mods_dir = os.path.join(CACHE_DIR, "mods")
    if os.path.isdir(mods_dir):
        mod_count = len([f for f in os.listdir(mods_dir) if f.endswith(".json")])
        result["mods/"] = {"cached_count": mod_count}

    return result
