"""CF bypass via DrissionPage headed browser + DOM extraction."""

import os
import shutil
import time
import logging
from typing import Optional, List
from DrissionPage import ChromiumPage, ChromiumOptions

from . import cache
from .parse import parse_best_mods

logger = logging.getLogger(__name__)

BASE_URL = "https://swgoh.gg"
CF_WAIT_TIMEOUT = 30  # seconds
SPA_RENDER_WAIT = 3   # seconds after CF clears

# Candidate browser paths (order: Chrome > Chromium > Edge)
_BROWSER_CANDIDATES: List[str] = [
    # Linux
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
    "/snap/bin/chromium",
    # macOS
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]

_page: Optional[ChromiumPage] = None


def _find_browser() -> str:
    """Find an available Chromium-based browser."""
    for path in _BROWSER_CANDIDATES:
        if os.path.isfile(path):
            return path
    # Fallback: try 'which'
    for cmd in ["google-chrome", "chromium-browser", "chromium", "microsoft-edge"]:
        found = shutil.which(cmd)
        if found:
            return found
    raise RuntimeError(
        "No Chromium-based browser found. Install Chrome, Chromium, or Edge."
    )


def _ensure_page() -> ChromiumPage:
    """Get or create a persistent DrissionPage browser session."""
    global _page
    if _page is not None:
        try:
            _page.title
            return _page
        except Exception:
            _page = None

    browser_path = _find_browser()
    logger.info("Using browser: %s", browser_path)

    co = ChromiumOptions()
    co.set_browser_path(browser_path)
    co.set_argument("--disable-blink-features=AutomationControlled")
    co.auto_port()
    co.headless(False)  # CF Turnstile requires headed mode
    _page = ChromiumPage(co)
    return _page


def _wait_cf_clear(page: ChromiumPage, timeout: int = CF_WAIT_TIMEOUT) -> bool:
    """Wait for Cloudflare challenge to resolve."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            title = page.title or ""
            if "just a moment" not in title.lower() and "请稍候" not in title.lower():
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def _close_page():
    """Close the browser page."""
    global _page
    if _page is not None:
        try:
            _page.quit()
        except Exception:
            pass
        _page = None


def fetch_page_html(url: str, cache_key: Optional[str] = None,
                    force: bool = False) -> Optional[str]:
    """Fetch a CF-protected page HTML via DrissionPage.

    Args:
        url: Full URL to fetch.
        cache_key: Cache key for storing result. If None, no caching.
        force: Bypass cache and re-fetch.

    Returns:
        Raw HTML string, or None on failure.
    """
    if cache_key and not force:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    logger.info("Fetching %s via DrissionPage...", url)

    try:
        page = _ensure_page()
        page.get(url)

        if not _wait_cf_clear(page):
            logger.error("CF challenge not resolved within %ds", CF_WAIT_TIMEOUT)
            return None

        time.sleep(SPA_RENDER_WAIT)

        html = page.html
        if not html or len(html) < 500:
            logger.error("Page HTML too short, likely did not load properly")
            return None

        if cache_key:
            cache.set(cache_key, html)
        return html

    except Exception as e:
        logger.error("DrissionPage fetch failed: %s", e)
        _close_page()
        return None


def fetch_best_mods(slug: str, slice_name: str = "KYBER",
                    force: bool = False):
    """Fetch and parse best-mods for a character.

    Returns:
        BestMods dataclass, or None on failure.
    """
    url = f"{BASE_URL}/characters/{slug}/best-mods/"
    html = fetch_page_html(url, cache_key=f"mods/{slug}", force=force)
    if html is None:
        return None
    return parse_best_mods(html, slug, slice_name)


def fetch_gac_counters(base_id: str, season_id: Optional[str] = None,
                       sort: str = "win_pct", exclude_gl: bool = False,
                       division: Optional[str] = None,
                       force: bool = False) -> Optional[dict]:
    """Fetch and parse GAC counters page for a character.

    Args:
        base_id: Character base_id (e.g. 'BOKATAN')
        season_id: Optional season ID
        sort: Sort by 'win_pct', 'count', or 'banners'
        exclude_gl: Exclude Galactic Legends
        division: Division filter
        force: Bypass cache

    Returns:
        Dict with 'character', 'season', 'counters' list, or None on failure.
    """
    import re

    url = f"{BASE_URL}/gac/counters/{base_id}/"
    params = []
    if season_id:
        params.append(f"season_id={season_id}")
    if sort != "win_pct":
        params.append(f"sort={sort}")
    if exclude_gl:
        params.append("exclude_gl=1")
    if division:
        params.append(f"division={division}")
    if params:
        url += "?" + "&".join(params)

    cache_key = f"gac-counters/{base_id}"
    html = fetch_page_html(url, cache_key=cache_key, force=force)
    if html is None:
        return None

    # Parse counters from HTML
    # Each counter row is in a div.panel--size-sm
    # Attack: data-unit-def-tooltip-app with a_lead= / a_member= in href
    # Defense: data-unit-def-tooltip-app (right side, no a_lead/a_member in href)
    # Stats: Seen / Win % / Avg

    counters = []
    rows = re.split(r'panel--size-sm', html)

    for row in rows[1:]:  # skip first split (before first row)
        # Extract attack team: a_lead= and a_member= from hrefs
        attack_ids = []
        lead_match = re.search(r'a_lead=([A-Z0-9]+)', row)
        if lead_match:
            attack_ids.append(lead_match.group(1))
        for m in re.finditer(r'a_member=([A-Z0-9]+)', row):
            attack_ids.append(m.group(1))

        # Extract defense team: data-unit-def-tooltip-app after the stats section
        # Split row into attack side and defense side by finding the stats section
        stats_section = re.search(r'Seen.*?Win\s*%.*?Avg.*?(\d+\.?\d*)\s*</div>', row, re.DOTALL)
        if not stats_section:
            continue

        defense_part = row[stats_section.end():]
        defense_ids = re.findall(r'data-unit-def-tooltip-app="([A-Z0-9]+)"', defense_part)
        # Also check d_lead/d_member
        d_lead = re.search(r'd_lead=([A-Z0-9]+)', defense_part)
        d_members = re.findall(r'd_member=([A-Z0-9]+)', defense_part)
        if d_lead or d_members:
            defense_ids = []
            if d_lead:
                defense_ids.append(d_lead.group(1))
            defense_ids.extend(d_members)

        # Extract stats
        seen_match = re.search(r'Seen.*?<div class="font-bold">(\d+)', row, re.DOTALL)
        win_match = re.search(r'Win\s*%.*?<div class="font-bold">(\d+\.?\d*)%?', row, re.DOTALL)
        avg_match = re.search(r'Avg.*?<div class="font-bold">(\d+\.?\d*)', row, re.DOTALL)

        if not attack_ids or not defense_ids:
            continue

        counters.append({
            "attack": attack_ids,
            "defense": defense_ids,
            "seen": int(seen_match.group(1)) if seen_match else 0,
            "win_pct": float(win_match.group(1)) if win_match else 0.0,
            "avg_banners": float(avg_match.group(1)) if avg_match else 0.0,
        })

    # Extract season info
    season_match = re.search(r'Season\s+(\d+)', html)
    season = f"Season {season_match.group(1)}" if season_match else "Unknown"

    # Extract battle count
    count_match = re.search(r'Based on\s*<[^>]*>([\d,]+)</[^>]*>\s*battles', html)
    battle_count = int(count_match.group(1).replace(',', '')) if count_match else 0

    return {
        "character": base_id,
        "season": season,
        "battle_count": battle_count,
        "counters": counters,
    }
