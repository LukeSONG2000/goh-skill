#!/usr/bin/env python3
"""SWGOH data CLI — characters, abilities, ships, gear, GAC counters, best mods."""

import argparse
import json
import sys
import os

# Add lib to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import api, browser, cache, parse, names as names_lib
from lib.parse import character_stats_to_markdown


def _resolve_name(query: str):
    """Resolve a query to (base_id, slug) using names database.

    Returns (base_id, slug) or (None, None).
    """
    results = names_lib.search(query)
    if results:
        bid, entry = results[0]
        return bid, entry.get("slug", "")
    return None, None


# --- Subcommand handlers ---

def cmd_names(args):
    sub = args.subcommand

    if sub == "init":
        chars = api.fetch_characters(force=args.force)
        ships = api.fetch_ships(force=args.force)
        data = names_lib.init_from_api(chars, ships)
        st = names_lib.stats(data)
        print(f"Initialized: {st['characters']} characters + {st['ships']} ships")
        print(f"Existing cn: {st['with_cn']}, nicknames: {st['with_nickname']}")

    elif sub == "search":
        results = names_lib.search(args.query)
        if not results:
            print(f"No match for: {args.query}")
            return
        for bid, entry in results[:args.limit]:
            cn = entry.get("cn", "")
            nick = entry.get("nickname", "")
            extra = ""
            if cn:
                extra += f" | CN: {cn}"
            if nick:
                extra += f" | Nick: {nick}"
            if not extra:
                extra = " | (no cn/nickname yet)"
            print(f"  {entry['name']} ({bid}) [{entry['type']}]{extra}")

    elif sub == "update":
        ok = names_lib.update(args.base_id, cn=args.cn, nickname=args.nickname)
        if ok:
            entry = names_lib.search(args.base_id)
            if entry:
                _, e = entry[0]
                print(f"Updated {args.base_id}: cn={e.get('cn','')} nick={e.get('nickname','')}")
        else:
            print(f"Not found: {args.base_id}", file=sys.stderr)
            sys.exit(1)

    elif sub == "stats":
        st = names_lib.stats()
        print(f"Total: {st['total']} ({st['characters']} chars, {st['ships']} ships)")
        print(f"With CN: {st['with_cn']} | With nickname: {st['with_nickname']}")
        print(f"Missing CN: {st['missing_cn']} | Missing nickname: {st['missing_nickname']}")

    elif sub == "missing":
        missing = names_lib.get_untranslated()
        for bid, entry in missing:
            print(f"  {entry['name']} ({bid}) [{entry['type']}]")
        print(f"\nTotal missing: {len(missing)}")

    elif sub == "export":
        data = names_lib.get_all()
        if args.json:
            json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
        else:
            # TSV format: base_id, name, type, cn, nickname
            print("base_id\tname\ttype\tcn\tnickname")
            for bid, entry in data.items():
                print(f"{bid}\t{entry['name']}\t{entry['type']}\t{entry.get('cn','')}\t{entry.get('nickname','')}")

    else:
        print(f"Unknown names subcommand: {sub}", file=sys.stderr)
        sys.exit(1)


def cmd_characters(args):
    data = api.fetch_characters(force=args.force)
    if args.json:
        json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
        return
    name_map = {e["base_id"]: e for e in names_lib.get_all().values()}
    for c in data:
        name = c.get("name", "?")
        base_id = c.get("base_id", "?")
        url = c.get("url", "")
        slug = url.strip("/").split("/")[-1] if url else "?"
        cats = ", ".join(c.get("categories", []))
        role = c.get("role", "")
        align = c.get("alignment", "")
        ac = ", ".join(c.get("ability_classes", []))
        nm = name_map.get(base_id, {})
        cn = nm.get("cn", "")
        nick = nm.get("nickname", "")
        extra = ""
        if cn:
            extra += f" | {cn}"
        if nick:
            extra += f" ({nick})"
        print(f"{name} ({base_id}){extra} | {align} {role} | {cats} | AC: {ac}")


def cmd_abilities(args):
    data = api.fetch_abilities(force=args.force)
    if args.json:
        json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
        return
    if args.filter:
        kw = args.filter.lower()
        data = [a for a in data if kw in json.dumps(a).lower()]
    for a in data:
        name = a.get("name", "?")
        base_id = a.get("character_base_id", "?")
        cid = a.get("combat_type", "?")
        is_zeta = a.get("is_zeta", False)
        is_omega = a.get("is_omega", False)
        tags = []
        if is_zeta:
            tags.append("ZETA")
        if is_omega:
            tags.append("OMEGA")
        tag_str = f" [{', '.join(tags)}]" if tags else ""
        print(f"{name} -> {base_id} (combat_type={cid}){tag_str}")


def cmd_ships(args):
    data = api.fetch_ships(force=args.force)
    if args.json:
        json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
        return
    name_map = {e["base_id"]: e for e in names_lib.get_all().values()}
    for s in data:
        name = s.get("name", "?")
        base_id = s.get("base_id", "?")
        url = s.get("url", "")
        slug = url.strip("/").split("/")[-1] if url else "?"
        nm = name_map.get(base_id, {})
        cn = nm.get("cn", "")
        nick = nm.get("nickname", "")
        extra = ""
        if cn:
            extra += f" | {cn}"
        if nick:
            extra += f" ({nick})"
        print(f"{name} ({base_id}){extra} | {slug}")


def cmd_gear(args):
    data = api.fetch_gear(force=args.force)
    if args.json:
        json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
        return
    for g in data:
        name = g.get("name", "?")
        gid = g.get("id", "?")
        tier = g.get("tier", "?")
        print(f"{name} (id={gid}, tier={tier})")


def cmd_gac(args):
    sub = args.subcommand
    if sub == "config":
        data = api.fetch_gac_config(force=args.force)
        if args.json:
            json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
        else:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    if sub == "counters":
        base_id, slug = _resolve_name(args.character)
        if not base_id:
            print(f"Character not found: {args.character}", file=sys.stderr)
            sys.exit(1)

        data = browser.fetch_gac_counters(
            base_id,
            season_id=args.season_id,
            sort=args.sort,
            exclude_gl=args.exclude_gl,
            force=args.force,
        )
        if data is None:
            print(f"Failed to fetch counters for {base_id}", file=sys.stderr)
            sys.exit(1)

        # Resolve base_ids to names
        all_names = names_lib.get_all()

        if args.json:
            json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
        else:
            entry = all_names.get(base_id, {})
            display = entry.get("cn") or entry.get("nickname") or entry.get("name") or base_id
            print(f"# GAC Counters for {display} ({data['season']})")
            print(f"Based on {data['battle_count']:,} battles\n")
            for i, c in enumerate(data["counters"], 1):
                atk_names = [all_names.get(bid, {}).get("name", bid) for bid in c["attack"]]
                dfn_names = [all_names.get(bid, {}).get("name", bid) for bid in c["defense"]]
                atk = " + ".join(atk_names)
                dfn = " + ".join(dfn_names)
                print(f"{i}. ATK [{atk}] -> DEF [{dfn}]")
                print(f"   Seen: {c['seen']} | Win: {c['win_pct']}% | Avg Banners: {c['avg_banners']}")
                print()
    else:
        print(f"Unknown GAC subcommand: {sub}", file=sys.stderr)
        sys.exit(1)


def cmd_stats(args):
    base_id, slug = _resolve_name(args.character)
    if not slug:
        print(f"Character not found: {args.character}", file=sys.stderr)
        sys.exit(1)

    stats = browser.fetch_character_stats(
        slug,
        gear_tier=args.gear_tier,
        force=args.force,
    )
    if stats is None:
        print(f"Failed to fetch stats for {slug}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        json.dump(stats, sys.stdout, ensure_ascii=False, indent=2)
    else:
        # Resolve CN name if available
        all_names = names_lib.get_all()
        entry = all_names.get(base_id, {})
        cn = entry.get("cn", "")
        if cn and "name" in stats:
            stats["name"] = f"{stats['name']}（{cn}）"
        output = character_stats_to_markdown(stats)
        # Warn if requested gear tier wasn't available
        if args.gear_tier and stats.get("gear_tier") != args.gear_tier:
            from lib.parse import GEAR_CN
            requested = GEAR_CN.get(args.gear_tier, args.gear_tier)
            actual = GEAR_CN.get(stats["gear_tier"], stats["gear_tier"])
            output = f"**注意：该角色不支持 {requested}，显示的是 {actual} 数据**\n\n" + output
        print(output)


def cmd_mods(args):
    base_id, slug = _resolve_name(args.character)
    if not slug:
        print(f"Character not found: {args.character}", file=sys.stderr)
        sys.exit(1)

    if args.batch:
        queries = [s.strip() for s in args.character.split(",")]
        results = {}
        for q in queries:
            bid, s = _resolve_name(q)
            if s:
                mods = browser.fetch_best_mods(s, args.slice, args.force)
                if mods:
                    results[s] = parse.best_mods_to_dict(mods)
                else:
                    results[s] = {"error": "fetch failed"}
        json.dump(results, sys.stdout, ensure_ascii=False, indent=2)
        return

    mods = browser.fetch_best_mods(slug, args.slice, args.force)
    if mods is None:
        print(f"Failed to fetch mods for {slug}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        json.dump(parse.best_mods_to_dict(mods), sys.stdout, ensure_ascii=False, indent=2)
    else:
        print(parse.best_mods_to_markdown(mods))


def cmd_search(args):
    query = args.query.lower()
    chars = api.fetch_characters()
    abilities = api.fetch_abilities()

    print("=== Characters ===")
    for c in chars:
        blob = json.dumps(c).lower()
        if query in blob:
            name = c.get("name", "?")
            base_id = c.get("base_id", "?")
            cats = ", ".join(c.get("categories", []))
            ac = ", ".join(c.get("ability_classes", []))
            print(f"  {name} ({base_id}) | Categories: {cats} | AC: {ac}")

    print("\n=== Abilities ===")
    for a in abilities:
        blob = json.dumps(a).lower()
        if query in blob:
            name = a.get("name", "?")
            char = a.get("character_base_id", "?")
            is_zeta = a.get("is_zeta", False)
            print(f"  {name} -> {char} {'[ZETA]' if is_zeta else ''}")


def cmd_cache(args):
    if args.clear:
        cleared = cache.clear(args.key)
        print(f"Cleared: {', '.join(cleared) if cleared else 'nothing'}")
        return

    status = cache.status()
    if args.json:
        json.dump(status, sys.stdout, ensure_ascii=False, indent=2)
    else:
        print("Cache status:")
        for key, info in status.items():
            if isinstance(info, dict) and "fresh" in info:
                state = "FRESH" if info["fresh"] else "STALE"
                age = info.get("age_seconds", 0)
                ttl = info.get("ttl_seconds", 0)
                size = info.get("size_bytes", 0)
                print(f"  {key}: {state} (age={age}s / ttl={ttl}s, {size}B)")
            else:
                print(f"  {key}: {info}")


def cmd_webstore(args):
    """Delegate SWGOH Web Store automation to the Node long-running service client."""
    import subprocess

    base_dir = os.path.dirname(os.path.abspath(__file__))
    client = os.path.join(base_dir, "webstore", "bin", "goh-webstore.mjs")
    if not os.path.exists(client):
        print(f"Webstore client not found: {client}", file=sys.stderr)
        sys.exit(1)
    cmd = ["node", client] + list(args.webstore_args)
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


def main():
    # Pre-extract global flags before argparse
    argv = sys.argv[1:]
    use_json = "--json" in argv
    use_force = "--force" in argv
    argv = [a for a in argv if a not in ("--json", "--force")]

    parser = argparse.ArgumentParser(description="SWGOH data CLI")
    subparsers = parser.add_subparsers(dest="command")

    # names
    p_names = subparsers.add_parser("names", help="Name database management")
    names_sub = p_names.add_subparsers(dest="subcommand")
    names_sub.add_parser("init", help="Initialize from API (preserves existing cn/nick)")
    p_search = names_sub.add_parser("search", help="Search name database")
    p_search.add_argument("query", help="Search query (English, CN, nickname, base_id)")
    p_search.add_argument("--limit", type=int, default=10, help="Max results")
    p_update = names_sub.add_parser("update", help="Update cn/nickname for a character")
    p_update.add_argument("base_id", help="Character/ship base_id")
    p_update.add_argument("--cn", default="", help="Chinese name")
    p_update.add_argument("--nickname", default="", help="Nickname/abbreviation")
    names_sub.add_parser("stats", help="Name database statistics")
    names_sub.add_parser("missing", help="List entries missing cn or nickname")
    p_export = names_sub.add_parser("export", help="Export name database")
    p_export.add_argument("--json", action="store_true", help="JSON format (default: TSV)")

    # characters
    subparsers.add_parser("characters", help="List all characters")

    # abilities
    p_ab = subparsers.add_parser("abilities", help="List all abilities")
    p_ab.add_argument("--filter", help="Filter by keyword")

    # ships
    subparsers.add_parser("ships", help="List all ships")

    # gear
    subparsers.add_parser("gear", help="List all gear items")

    # gac
    p_gac = subparsers.add_parser("gac", help="GAC data")
    gac_sub = p_gac.add_subparsers(dest="subcommand")
    gac_sub.add_parser("config", help="GAC season config")
    p_counters = gac_sub.add_parser("counters", help="GAC counters for a character")
    p_counters.add_argument("character", help="Character name or base_id")
    p_counters.add_argument("--season-id", default=None, help="Season ID")
    p_counters.add_argument("--sort", default="win_pct", choices=["win_pct", "count", "banners"])
    p_counters.add_argument("--exclude-gl", action="store_true", help="Exclude Galactic Legends")

    # stats
    p_stats = subparsers.add_parser("stats", help="Character detail stats (Speed, Health, etc.)")
    p_stats.add_argument("character", help="Character name, base_id, or slug")
    p_stats.add_argument("--gear-tier", default=None,
                         help="Gear tier (e.g. RELIC_7). Default: Gear 12")

    # mods
    p_mods = subparsers.add_parser("mods", help="Best mods for a character")
    p_mods.add_argument("character", help="Character name, base_id, or slug")
    p_mods.add_argument("--slice", default="KYBER", help="Data slice")
    p_mods.add_argument("--batch", action="store_true", help="Batch mode (comma-separated slugs)")

    # search
    p_search = subparsers.add_parser("search", help="Search characters and abilities")
    p_search.add_argument("query", help="Search query")

    # cache
    p_cache = subparsers.add_parser("cache", help="Cache management")
    p_cache.add_argument("--clear", action="store_true", help="Clear cache")
    p_cache.add_argument("key", nargs="?", help="Specific cache key to clear")

    # webstore automation
    p_webstore = subparsers.add_parser("webstore", help="SWGOH Web Store login and free reward claiming automation")
    p_webstore.add_argument("webstore_args", nargs=argparse.REMAINDER,
                            help="Arguments passed to webstore client: status/login/email/code/claim/logs/install-service/start-service/stop-service")

    args = parser.parse_args(argv)
    args.json = use_json
    args.force = use_force

    if not args.command:
        parser.print_help()
        sys.exit(1)

    handlers = {
        "names": cmd_names,
        "characters": cmd_characters,
        "abilities": cmd_abilities,
        "ships": cmd_ships,
        "gear": cmd_gear,
        "gac": cmd_gac,
        "stats": cmd_stats,
        "mods": cmd_mods,
        "search": cmd_search,
        "cache": cmd_cache,
        "webstore": cmd_webstore,
    }
    handler = handlers.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
