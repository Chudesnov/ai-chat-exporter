import argparse
import sys
import os
from datetime import datetime

from . import opencode
from . import copilot
from . import claude
from .markdown import render_markdown
from .utils import sanitize_filename

def get_all_recent_sessions(days, sources):
    sessions = []
    if "opencode" in sources:
        sessions.extend(opencode.list_recent_sessions(days))
    if "copilot" in sources:
        sessions.extend(copilot.list_recent_sessions(days))
    if "claude" in sources:
        sessions.extend(claude.list_recent_sessions(days))
    
    sessions.sort(key=lambda x: x['time_created'], reverse=True)
    return sessions

def find_all_matches(query, sources):
    matches = []
    if "opencode" in sources:
        matches.extend(opencode.find_sessions_by_title(query))
    if "copilot" in sources:
        matches.extend(copilot.find_sessions_by_title(query))
    if "claude" in sources:
        matches.extend(claude.find_sessions_by_title(query))
        
    matches.sort(key=lambda x: x['time_created'], reverse=True)
    return matches

def cmd_list(args, sources):
    sessions = get_all_recent_sessions(args.days, sources)
    if not sessions:
        print("No sessions found.")
        return

    print(f"Sessions from the last {args.days} day(s):\n")
    for s in sessions:
        dt = datetime.fromtimestamp(s["time_created"] / 1000)
        src_label = f"[{s['source'][:2].upper()}]"
        print(f"  {dt.strftime('%Y-%m-%d %H:%M')}  {src_label}  {s['title']}")
        print(f"    id: {s['session_id']}")
    print(f"\n{len(sessions)} session(s) found.")

def cmd_export(args, sources):
    title_query = args.title
    matches = find_all_matches(title_query, sources)
    
    if not matches:
        print(f"No sessions found matching: '{title_query}'", file=sys.stderr)
        print("Use --list to see recent sessions.", file=sys.stderr)
        sys.exit(1)

    if len(matches) > 1 and not args.all:
        print(f"Found {len(matches)} matching sessions:")
        for i, m in enumerate(matches):
            dt = datetime.fromtimestamp(m["time_created"] / 1000)
            src_label = f"[{m['source'][:2].upper()}]"
            print(f"  [{i + 1}] {dt.strftime('%Y-%m-%d %H:%M')}  {src_label}  {m['title']}  ({m['session_id']})")
        print()
        if sys.stdin.isatty():
            choice = input("Export which? (number, 'a' for all, Enter for most recent): ").strip()
            if choice.lower() == "a":
                pass  # export all
            elif choice.isdigit() and 1 <= int(choice) <= len(matches):
                matches = [matches[int(choice) - 1]]
            else:
                matches = [matches[0]]
        else:
            print("Multiple matches — exporting most recent. Use --all for all.", file=sys.stderr)
            matches = [matches[0]]

    for match in matches:
        _export_one(match, args)

def _export_one(match: dict, args):
    print(f"Exporting: {match['title']} ({match['session_id']})…")
    
    # Hydrate the session object
    if match['source'] == 'opencode':
        session = opencode.fetch_session_details(match)
        default_dir = os.path.expanduser("~/Notes/Main/OpenCode Chat Archive")
    elif match['source'] == 'copilot':
        session = copilot.fetch_session_details(match)
        default_dir = os.path.expanduser("~/Notes/Main/Copilot Chat Archive")
    elif match['source'] == 'claude':
        session = claude.fetch_session_details(match)
        default_dir = os.path.expanduser("~/Notes/Main/Claude Chat Archive")
    else:
        print(f"Unknown source {match['source']}")
        return

    md = render_markdown(session)

    if args.output:
        out_path = args.output
    else:
        out_dir = os.environ.get("OBSIDIAN_DIR", default_dir)
        os.makedirs(out_dir, exist_ok=True)
        filename = sanitize_filename(match["title"]) + ".md"
        out_path = os.path.join(out_dir, filename)

    with open(out_path, "w") as f:
        f.write(md)

    turns = session.get("turns", [])
    total_response = sum(sum(len(str(t)) for t in turn.get("assistant", [])) for turn in turns)
    total_tools = sum(len(turn.get("tools", [])) for turn in turns)

    print(f"  → {out_path}")
    print(f"  {len(turns)} turns, {total_response:,} chars of response, {total_tools} tool calls")

def main():
    parser = argparse.ArgumentParser(
        prog="ai-chat-export",
        description="Unified exporter for OpenCode, Copilot, and Claude Code chat sessions to Markdown.",
    )

    parser.add_argument("title", nargs="?", help="Session title or ID (partial match)")
    parser.add_argument("--source", "-s", choices=["all", "opencode", "copilot", "claude"], default="all",
                        help="Which exporter to use (default: all)")
    parser.add_argument("--output", "-o", help="Output file path (overrides Obsidian dir)")
    parser.add_argument("--all", "-a", action="store_true", help="Export all matches")
    parser.add_argument("--list", "-l", action="store_true", help="List recent sessions")
    parser.add_argument("--days", "-d", type=int, default=7, help="Days to look back (default: 7)")

    args = parser.parse_args()

    sources = ["opencode", "copilot", "claude"] if args.source == "all" else [args.source]

    if args.list:
        cmd_list(args, sources)
    elif args.title:
        cmd_export(args, sources)
    else:
        parser.print_help()
