"""Direct API client for swgoh.gg /api/ endpoints (no CF protection)."""

from curl_cffi import requests as cffi_requests
import json
from typing import Optional, Union, Dict, List
from . import cache

BASE = "https://swgoh.gg/api"
V1 = "https://swgoh.gg/api/v1"

_SESSION = None


def _session():
    global _SESSION
    if _SESSION is None:
        _SESSION = cffi_requests.Session(impersonate="chrome")
    return _SESSION


def _fetch(url: str, params: Optional[dict] = None, timeout: int = 30) -> Union[dict, list]:
    """Fetch JSON from URL, raise on error."""
    r = _session().get(url, params=params, timeout=timeout)
    if r.status_code == 401:
        raise RuntimeError(
            f"401 Unauthorized for {url}. This endpoint requires authentication. "
            "Log in to swgoh.gg in your browser and the session cookie will be used automatically."
        )
    r.raise_for_status()
    return r.json()


def _cached_fetch(cache_key: str, url: str, params: Optional[dict] = None,
                  force: bool = False, ttl: Optional[int] = None):
    """Fetch with cache layer. Returns parsed JSON data."""
    if not force:
        data = cache.get(cache_key, ttl)
        if data is not None:
            return data

    data = _fetch(url, params)
    cache.set(cache_key, data)
    return data


# --- Public API ---


def fetch_characters(force: bool = False) -> List[dict]:
    """Fetch all characters (325+). Includes categories, ability_classes, role, alignment."""
    return _cached_fetch("characters", f"{BASE}/characters/?format=json", force=force)


def fetch_abilities(force: bool = False) -> List[dict]:
    """Fetch all abilities (1796+). Includes description, is_zeta/omega/omicron, character_base_id."""
    return _cached_fetch("abilities", f"{BASE}/abilities/?format=json", force=force)


def fetch_ships(force: bool = False) -> List[dict]:
    """Fetch all ships (70+)."""
    return _cached_fetch("ships", f"{BASE}/ships/?format=json", force=force)


def fetch_gear(force: bool = False) -> List[dict]:
    """Fetch all gear items (694+)."""
    return _cached_fetch("gear", f"{BASE}/gear/?format=json", force=force)


def fetch_gac_config(force: bool = False) -> Dict:
    """Fetch GAC season config: active season, events, squad sizes."""
    data = _cached_fetch("gac-config", f"{V1}/gac/config-data/?format=json", force=force)
    # API wraps in {"data": ..., "message": ..., "total_count": ...}
    return data.get("data", data) if isinstance(data, dict) else data


def fetch_gac_battles(
    combat_type: int = 1,
    squad_size: int = 5,
    league: str = "KYBER",
    show_latest_season: bool = True,
    page: int = 1,
    page_size: int = 50,
    season_id: Optional[str] = None,
    sort: str = "-count",
    force: bool = False,
) -> dict:
    """Fetch GAC counter/battle data.

    Returns dict with keys: totalCount, avgBanners, battles, percentage, performance.
    Each battle: attackLeadId, attackMemberIds, defenseLeadId, defenseMemberIds,
                 count, avgBanners, percentage (win rate).
    """
    params = {
        "combat_type": str(combat_type),
        "squad_size": str(squad_size),
        "league": league,
        "page": str(page),
        "page_size": str(page_size),
        "list_sort": sort,
    }
    if show_latest_season:
        params["show_latest_season"] = "true"
    if season_id:
        params["season_id"] = season_id

    data = _fetch(f"{V1}/gac/battle/battles/", params=params)
    return data.get("data", data) if isinstance(data, dict) else data


def fetch_gac_squads(
    combat_type: int = 1,
    squad_size: int = 5,
    league: str = "KYBER",
    show_latest_season: bool = True,
    season_id: Optional[str] = None,
    force: bool = False,
) -> dict:
    """Fetch top GAC squads by usage and win rate."""
    params = {
        "combat_type": str(combat_type),
        "squad_size": str(squad_size),
        "league": league,
    }
    if show_latest_season:
        params["show_latest_season"] = "true"
    if season_id:
        params["season_id"] = season_id

    data = _fetch(f"{V1}/gac/battle/squads/", params=params)
    return data.get("data", data) if isinstance(data, dict) else data


def fetch_gac_leaders(
    combat_type: int = 1,
    squad_size: int = 5,
    league: str = "KYBER",
    show_latest_season: bool = True,
    season_id: Optional[str] = None,
    force: bool = False,
) -> dict:
    """Fetch top GAC leaders by usage and win rate."""
    params = {
        "combat_type": str(combat_type),
        "squad_size": str(squad_size),
        "league": league,
    }
    if show_latest_season:
        params["show_latest_season"] = "true"
    if season_id:
        params["season_id"] = season_id

    data = _fetch(f"{V1}/gac/battle/leaders/", params=params)
    return data.get("data", data) if isinstance(data, dict) else data
