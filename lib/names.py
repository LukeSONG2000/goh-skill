"""Character/ship name mapping with Chinese translation and nickname support."""

import json
import os
import re
from typing import Optional, Dict, List, Tuple

NAMES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "names.json")


def _load() -> Dict:
    """Load names database from JSON file."""
    if os.path.exists(NAMES_FILE):
        with open(NAMES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save(data: Dict) -> None:
    """Save names database to JSON file."""
    with open(NAMES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def init_from_api(chars: list, ships: list) -> Dict:
    """Build initial names database from API data. Preserves existing cn/nickname."""
    existing = _load()
    data = {}

    for c in chars:
        base_id = c.get("base_id", "")
        url = c.get("url", "")
        slug = url.strip("/").split("/")[-1] if url else ""
        name = c.get("name", "")
        if not base_id or not name:
            continue
        old = existing.get(base_id, {})
        data[base_id] = {
            "name": name,
            "slug": slug,
            "type": "character",
            "cn": old.get("cn", ""),
            "nickname": old.get("nickname", ""),
        }

    for s in ships:
        base_id = s.get("base_id", "")
        url = s.get("url", "")
        slug = url.strip("/").split("/")[-1] if url else ""
        name = s.get("name", "")
        if not base_id or not name:
            continue
        old = existing.get(base_id, {})
        data[base_id] = {
            "name": name,
            "slug": slug,
            "type": "ship",
            "cn": old.get("cn", ""),
            "nickname": old.get("nickname", ""),
        }

    _save(data)
    return data


def search(query: str, data: Optional[Dict] = None) -> List[Tuple[str, Dict]]:
    """Search for a character/ship by any name field.

    Returns list of (base_id, entry) tuples, best match first.
    """
    if data is None:
        data = _load()
    if not data:
        return []

    q = query.lower().strip()
    results = []

    for base_id, entry in data.items():
        # Exact matches get higher priority
        score = 0
        name = entry.get("name", "").lower()
        cn = entry.get("cn", "").lower()
        nickname = entry.get("nickname", "").lower()
        bid = base_id.lower()
        slug = entry.get("slug", "").lower()

        # Exact base_id match
        if q == bid:
            score = 100
        # Exact name match
        elif q == name:
            score = 90
        # Exact cn/nickname match
        elif q == cn or q == nickname:
            score = 85
        # Exact slug match
        elif q == slug:
            score = 80
        # Partial matches
        elif q in name:
            score = 70 - name.index(q)
        elif q in cn:
            score = 65 - cn.index(q)
        elif q in nickname:
            score = 60 - nickname.index(q)
        elif q in slug:
            score = 55 - slug.index(q)
        elif q in bid:
            score = 50 - bid.index(q)
        # Abbreviation match: "JML" matches "Jedi Master Luke Skywalker"
        elif _is_abbreviation(q, name):
            score = 75
        elif _is_abbreviation(q, cn):
            score = 70

        if score > 0:
            results.append((base_id, entry, score))

    results.sort(key=lambda x: x[2], reverse=True)
    return [(bid, entry) for bid, entry, _ in results]


def _is_abbreviation(abbr: str, full_name: str) -> bool:
    """Check if abbr is a plausible abbreviation of full_name.

    E.g. "JML" matches "Jedi Master Luke Skywalker"
    (each letter of abbr matches the start of a word in full_name).
    """
    if not abbr or len(abbr) < 2 or len(abbr) > 5:
        return False
    words = full_name.split()
    if len(words) < len(abbr):
        return False
    abbr_upper = abbr.upper()
    for i, ch in enumerate(abbr_upper):
        if i >= len(words):
            return False
        if not words[i].upper().startswith(ch):
            return False
    return True


def update(base_id: str, cn: str = "", nickname: str = "") -> bool:
    """Update cn/nickname for a character/ship. Returns True if updated."""
    data = _load()
    if base_id not in data:
        return False
    if cn:
        data[base_id]["cn"] = cn
    if nickname:
        data[base_id]["nickname"] = nickname
    _save(data)
    return True


def get_all(data: Optional[Dict] = None) -> Dict:
    """Return full names database."""
    if data is None:
        data = _load()
    return data


def get_untranslated(data: Optional[Dict] = None) -> List[Tuple[str, Dict]]:
    """Return entries missing cn or nickname."""
    if data is None:
        data = _load()
    return [(bid, entry) for bid, entry in data.items()
            if not entry.get("cn") or not entry.get("nickname")]


def stats(data: Optional[Dict] = None) -> Dict:
    """Return statistics about the names database."""
    if data is None:
        data = _load()
    total = len(data)
    with_cn = sum(1 for e in data.values() if e.get("cn"))
    with_nick = sum(1 for e in data.values() if e.get("nickname"))
    chars = sum(1 for e in data.values() if e.get("type") == "character")
    ships_count = sum(1 for e in data.values() if e.get("type") == "ship")
    return {
        "total": total,
        "characters": chars,
        "ships": ships_count,
        "with_cn": with_cn,
        "with_nickname": with_nick,
        "missing_cn": total - with_cn,
        "missing_nickname": total - with_nick,
    }
