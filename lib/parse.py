"""Parse best-mods page content from swgoh.gg."""

import re
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional

# English → Chinese stat name mapping
STAT_CN = {
    "Power": "战力",
    "Health": "生命值",
    "Protection": "护盾",
    "Speed": "速度",
    "Critical Damage": "暴击伤害",
    "Critical Chance": "暴击率",
    "Potency": "效果命中",
    "Tenacity": "效果抵抗",
    "Health Steal": "生命偷取",
    "Defense Penetration": "防御穿透",
    "Armor Penetration": "护甲穿透",
    "Resistance Penetration": "抵抗穿透",
    "Accuracy": "精准",
    "Armor": "护甲",
    "Resistance": "抵抗",
    "Dodge Rating": "闪避",
    "Deflection Rating": "偏转",
    "Critical Avoidance": "暴击回避",
    "Damage": "伤害",
    "Mastery": "精通",
    # Base attributes
    "Strength (STR)": "力量（STR）",
    "Agility (AGI)": "敏捷（AGI）",
    "Tactics (TAC)": "战术（TAC）",
    "Strength Growth": "力量成长",
    "Agility Growth": "敏捷成长",
    "Tactics Growth": "战术成长",
    # Section names
    "Base Attributes": "基础属性",
    "General": "通用属性",
    "Physical Offense": "物理进攻",
    "Physical Survivability": "物理防御",
    "Special Offense": "特殊进攻",
    "Special Survivability": "特殊防御",
    "Overview": "概览",
}

# Gear tier display names
GEAR_CN = {
    "GEAR_12": "Gear 12",
    "GEAR_12_3": "Gear 12+3",
    "GEAR_12_5": "Gear 12+5",
    "GEAR_13": "Gear 13",
}
for i in range(1, 11):
    GEAR_CN[f"RELIC_{i}"] = f"Relic {i}"


def _stat_cn(en: str) -> str:
    """Translate English stat name to Chinese, keeping English in parentheses."""
    cn = STAT_CN.get(en)
    if cn:
        return cn
    return en


def _stat_header(en: str) -> str:
    """Format stat name as: 中文（English）or just English if no translation."""
    cn = STAT_CN.get(en)
    if cn and cn != en:
        return f"{cn}（{en}）"
    return en


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


def parse_character_stats(html: str, slug: str) -> dict:
    """Parse character stats from /units/{slug}/ page HTML.

    Returns dict with:
        base_id, name, slug, gear_tier, power,
        sections: {section_name: {stat_name: value, ...}, ...}
    """
    result = {
        "slug": slug,
        "sections": {},
    }

    # Extract base_id from data-base-id
    m = re.search(r'data-base-id="([A-Z0-9]+)"', html)
    if m:
        result["base_id"] = m.group(1)

    # Extract character name from title
    m = re.search(r'<title>([^|<]+)', html)
    if m:
        name = m.group(1).strip()
        # Clean: "Jedi Knight Luke Skywalker - Star Wars Galaxy of Heroes - SWGOH.GG"
        # → "Jedi Knight Luke Skywalker"
        for suffix in [" - Star Wars Galaxy of Heroes", " - SWGOH.GG", "SWGOH.GG"]:
            name = name.replace(suffix, "")
        result["name"] = name.strip().strip("-").strip()

    # Extract selected gear tier (or default first option)
    selected = re.search(r'<option[^>]*selected[^>]*value="([^"]+)"', html)
    if selected:
        result["gear_tier"] = selected.group(1)
    else:
        first_opt = re.search(r'<option\s+value="([^"]+)"', html)
        if first_opt:
            result["gear_tier"] = first_opt.group(1)

    # Parse sections and stats directly from full HTML
    # (the stat-table-data div is deeply nested, regex boundary detection is unreliable)
    current_section = "Overview"
    sections = {}

    # Build ordered list of (position, type, content) to sort titles before entries
    items = []

    # Find all section titles
    for title_m in re.finditer(r'stat-table-data__title">(.*?)</div>', html, re.DOTALL):
        section_name = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
        if section_name:
            items.append((title_m.start(), "title", section_name))

    # Find all label + value pairs
    for entry_m in re.finditer(
        r'stat-table-data__entry-primary-label">(.*?)</div>\s*'
        r'<div class="stat-table-data__entry-primary-value">(.*?)</div>',
        html, re.DOTALL
    ):
        raw_label = entry_m.group(1).strip()
        raw_value = entry_m.group(2).strip()
        label = re.sub(r'<[^>]+>', '', raw_label).strip()
        value = re.sub(r'<[^>]+>', '', raw_value).strip()
        if label and value:
            items.append((entry_m.start(), "entry", (label, value)))

    # Process in order so titles set the current_section before entries
    items.sort(key=lambda x: x[0])
    for pos, item_type, content in items:
        if item_type == "title":
            current_section = content
            if current_section not in sections:
                sections[current_section] = {}
        elif item_type == "entry":
            label, value = content
            if current_section not in sections:
                sections[current_section] = {}

            num_val = value.replace(',', '').replace('%', '')
            try:
                num_val = float(num_val)
                if num_val == int(num_val) and '%' not in value:
                    num_val = int(num_val)
                sections[current_section][label] = {"display": value, "value": num_val}
            except ValueError:
                sections[current_section][label] = {"display": value, "value": value}

            if label == "Power":
                result["power"] = value

    result["sections"] = sections
    return result


def character_stats_to_markdown(stats: dict) -> str:
    """Format character stats as Markdown with Chinese translations."""
    lines = []
    name = stats.get("name", stats.get("slug", ""))
    base_id = stats.get("base_id", "")
    gear = stats.get("gear_tier", "Unknown")
    power = stats.get("power", "")

    header = name
    if base_id:
        header += f"（{base_id}）"
    lines.append(f"# {header}")
    gear_display = GEAR_CN.get(gear, gear)
    lines.append(f"装备等级: {gear_display}" + (f" | 战力（Power）: {power}" if power else ""))
    lines.append("")

    sections = stats.get("sections", {})
    for section_name, stats_dict in sections.items():
        lines.append(f"## {_stat_cn(section_name)}")
        lines.append("| 属性 | 数值 |")
        lines.append("|------|------|")
        for stat_name, stat_val in stats_dict.items():
            display = stat_val["display"] if isinstance(stat_val, dict) else stat_val
            label = _stat_header(stat_name)
            lines.append(f"| {label} | {display} |")
        lines.append("")

    return "\n".join(lines)


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
