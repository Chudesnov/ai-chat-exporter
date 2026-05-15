import json
import os
import glob
import sqlite3
import time

from .vscode_parser import iter_workspace_dirs, read_session_index, find_vscode_jsonl, parse_vscode_jsonl

def find_sessions_by_title(title_query: str) -> list[dict]:
    results = []
    seen_ids = set()
    query_lower = title_query.lower()

    for ws_dir in iter_workspace_dirs():
        entries = read_session_index(ws_dir)
        for sid, entry in entries.items():
            if sid in seen_ids or sid.startswith("claude-code:/"):
                continue
            session_title = entry.get("title", "")
            if query_lower in session_title.lower() or query_lower in sid.lower():
                jsonl = find_vscode_jsonl(sid)
                if not jsonl and entry.get("isExternal", False):
                    continue
                results.append({
                    "session_id": sid,
                    "title": session_title,
                    "time_created": entry.get("lastMessageDate", 0),
                    "source": "copilot",
                    "jsonl_path": jsonl,
                    "jsonl_size": os.path.getsize(jsonl) if jsonl else 0,
                    "workspace": os.path.basename(ws_dir),
                })
                seen_ids.add(sid)

    results.sort(key=lambda r: r["time_created"], reverse=True)
    return results

def list_recent_sessions(days: int = 2) -> list[dict]:
    cutoff = (time.time() - days * 86400) * 1000
    results = []
    seen_ids = set()

    for ws_dir in iter_workspace_dirs():
        entries = read_session_index(ws_dir)
        for sid, entry in entries.items():
            if sid in seen_ids or sid.startswith("claude-code:/"):
                continue
            ts = entry.get("lastMessageDate", 0)
            if ts > cutoff and not entry.get("isEmpty", True):
                jsonl = find_vscode_jsonl(sid)
                if not jsonl and entry.get("isExternal", False):
                    continue
                results.append({
                    "session_id": sid,
                    "title": entry.get("title", "New Chat"),
                    "time_created": ts,
                    "source": "copilot",
                    "jsonl_path": jsonl,
                    "workspace": os.path.basename(ws_dir),
                })
                seen_ids.add(sid)

    results.sort(key=lambda r: r["time_created"], reverse=True)
    return results

def fetch_session_details(session: dict) -> dict:
    if not session.get("jsonl_path") or not os.path.exists(session["jsonl_path"]):
        session["turns"] = []
        return session
        
    parsed = parse_vscode_jsonl(session["jsonl_path"])
    session["turns"] = parsed.get("turns", [])
    return session
