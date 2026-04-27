"""Parse best-mods page content from swgoh.gg."""

import re
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional


@dataclass
class ModSetEntry:
    name: str
    pct: float


@dataclass
class SlotPrimary:
    stat: str
    pct: float


@dataclass
class SecondaryFocus:
    name: str
    avg: float
    pct: float


@dataclass
class BestMods:
    slug: str
    slice: str = "KYBER"
    sample_size: int = 0
    most_popular_set: str = ""
    primary_set: List[ModSetEntry] = field(default_factory=list)
    secondary_set: List[ModSetEntry] = field(default_factory=list)
    specific_sets: List[ModSetEntry] = field(default_factory=list)
    arrow: List[SlotPrimary] = field(default_factory=list)
    triangle: List[SlotPrimary] = field(default_factory=list)
    circle: List[SlotPrimary] = field(default_factory=list)
    cross: List[SlotPrimary] = field(default_factory=list)
    secondary_focus: List[SecondaryFocus] = field(default_factory=list)
    relic_avg: float = 0.0
    avg_stats: dict = field(default_factory=dict)


def _strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _parse_pct_pairs(text: str) -> List[ModSetEntry]:
    """Parse sequences like 'Crit Damage32.1%Offense19.5%Speed16.5%'."""
    results = []
    # Match: Name followed by number%
    # Names can be multi-word (e.g., "Crit Damage", "Critical Avoidance")
    pattern = r'([A-Z][A-Za-z\s]+?)(\d+\.?\d*%)'
    for m in re.finditer(pattern, text):
        name = m.group(1).strip()
        pct = float(m.group(2).rstrip('%'))
        if name and pct >= 0:
            results.append(ModSetEntry(name=name, pct=pct))
    return results


def _parse_slot_primaries(text: str) -> List[SlotPrimary]:
    """Parse slot primary stats like 'Speed95.93%Offense2.9%'."""
    results = []
    pattern = r'([A-Z][A-Za-z\s]+?)(\d+\.?\d*%)'
    for m in re.finditer(pattern, text):
        name = m.group(1).strip()
        pct = float(m.group(2).rstrip('%'))
        if name and pct >= 0:
            results.append(SlotPrimary(stat=name, pct=pct))
    return results


def _parse_secondary_focus(text: str) -> List[SecondaryFocus]:
    """Parse secondary focus like 'Speed+20.6 avg21%Potency+5.90%avg10%'."""
    results = []
    # Pattern: Name +value avg pct% or Name +value% avg pct%
    pattern = r'([A-Z][A-Za-z\s]+?)\+?([\d.]+%?)\s*avg\s*(\d+\.?\d*%)'
    for m in re.finditer(pattern, text):
        name = m.group(1).strip()
        avg_str = m.group(2).rstrip('%')
        pct = float(m.group(3).rstrip('%'))
        try:
            avg = float(avg_str)
        except ValueError:
            avg = 0.0
        if name:
            results.append(SecondaryFocus(name=name, avg=avg, pct=pct))
    return results


def _extract_section(text: str, start_marker: str, end_marker: str) -> str:
    """Extract text between two markers."""
    start = text.find(start_marker)
    if start == -1:
        return ""
    start += len(start_marker)
    end = text.find(end_marker, start)
    if end == -1:
        return text[start:]
    return text[start:end]


def parse_best_mods(html: str, slug: str, slice_name: str = "KYBER") -> BestMods:
    """Parse best-mods page HTML into structured BestMods data."""
    text = _strip_html(html)
    result = BestMods(slug=slug, slice=slice_name)

    # Sample size: "Based on 1,000 units" or "Based on X units"
    m = re.search(r'Based on ([\d,]+) units', text)
    if m:
        result.sample_size = int(m.group(1).replace(',', ''))

    # Most popular mod set: "The most popular Mod Set for ... is X + Y (Z%). ..."
    m = re.search(r'The most popular Mod Set for .*? is (.+?)\. This set provides', text)
    if m:
        result.most_popular_set = m.group(1).strip()

    # Primary Set
    section = _extract_section(text, "Primary Set", "Secondary Set")
    if section:
        result.primary_set = _parse_pct_pairs(section)

    # Secondary Set
    section = _extract_section(text, "Secondary Set", "Arrow")
    if not section:
        section = _extract_section(text, "Secondary Set", "Specific Mod Sets")
    if section:
        result.secondary_set = _parse_pct_pairs(section)

    # Specific mod sets (detailed breakdown)
    section = _extract_section(text, "Show specific sets", "Arrow")
    if not section:
        # Try alternate: after secondary sets, before Arrow
        idx_arrow = text.find("Arrow")
        idx_specific = text.find("specific sets")
        if idx_specific != -1 and idx_arrow != -1 and idx_specific < idx_arrow:
            section = text[idx_specific:idx_arrow]
    if section:
        result.specific_sets = _parse_pct_pairs(section)

    # Slot primaries: Arrow, Triangle, Circle, Cross
    for slot_name in ["Arrow", "Triangle", "Circle", "Cross"]:
        next_slots = ["Triangle", "Circle", "Cross", "Secondary Stat Focus"]
        idx = ["Arrow", "Triangle", "Circle", "Cross"].index(slot_name)
        end_marker = next_slots[idx] if idx < len(next_slots) else "Relic"
        section = _extract_section(text, slot_name, end_marker)
        if not section:
            continue
        parsed = _parse_slot_primaries(section)
        setattr(result, slot_name.lower(), parsed)

    # Secondary Stat Focus
    section = _extract_section(text, "Secondary Stat Focus", "Relic")
    if section:
        result.secondary_focus = _parse_secondary_focus(section)

    # Relic average
    m = re.search(r'Relic\s+([\d.]+)', text)
    if m:
        try:
            result.relic_avg = float(m.group(1))
        except ValueError:
            pass

    # Average stats section
    avg_section = _extract_section(text, "Average Stats", "Best Mod Set")
    if avg_section:
        # Parse stat lines like "Health 61,683 (+6883)"
        stat_pattern = r'([A-Za-z\s]+?)([\d,]+)\s*\(([\d,]+)\)'
        for m in re.finditer(stat_pattern, avg_section):
            stat_name = m.group(1).strip()
            stat_val = m.group(2).replace(',', '')
            stat_diff = m.group(3).replace(',', '')
            if stat_name:
                try:
                    result.avg_stats[stat_name] = {
                        "value": int(stat_val),
                        "bonus": int(stat_diff),
                    }
                except ValueError:
                    pass

    return result


def best_mods_to_dict(mods: BestMods) -> dict:
    """Convert BestMods to a JSON-serializable dict."""
    d = asdict(mods)
    return d


def best_mods_to_markdown(mods: BestMods) -> str:
    """Format BestMods as human-readable Markdown."""
    lines = [f"# Best Mods for {mods.slug} ({mods.slice})"]
    lines.append(f"Sample: {mods.sample_size:,} units | Relic avg: {mods.relic_avg}")
    lines.append(f"Most popular set: {mods.most_popular_set}")
    lines.append("")

    if mods.primary_set:
        lines.append("## Primary Set")
        lines.append("| Set | Usage |")
        lines.append("|-----|-------|")
        for s in mods.primary_set:
            lines.append(f"| {s.name} | {s.pct:.1f}% |")
        lines.append("")

    if mods.secondary_set:
        lines.append("## Secondary Set")
        lines.append("| Set | Usage |")
        lines.append("|-----|-------|")
        for s in mods.secondary_set:
            lines.append(f"| {s.name} | {s.pct:.1f}% |")
        lines.append("")

    for slot in ["arrow", "triangle", "circle", "cross"]:
        items = getattr(mods, slot, [])
        if items:
            lines.append(f"## {slot.title()}")
            lines.append("| Stat | Usage |")
            lines.append("|------|-------|")
            for s in items:
                lines.append(f"| {s.stat} | {s.pct:.1f}% |")
            lines.append("")

    if mods.secondary_focus:
        lines.append("## Secondary Stat Focus")
        lines.append("| Stat | Avg | Usage |")
        lines.append("|------|-----|-------|")
        for s in mods.secondary_focus:
            lines.append(f"| {s.name} | +{s.avg} | {s.pct:.1f}% |")
        lines.append("")

    if mods.avg_stats:
        lines.append("## Average Stats")
        lines.append("| Stat | Value | Bonus |")
        lines.append("|------|-------|-------|")
        for name, vals in mods.avg_stats.items():
            lines.append(f"| {name} | {vals['value']:,} | +{vals['bonus']:,} |")

    return "\n".join(lines)
