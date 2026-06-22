import json
import os
import glob
import sqlite3
import time

from .vscode_parser import (
    iter_workspace_dirs,
    read_session_index,
    find_vscode_jsonl,
    parse_vscode_jsonl,
    COPILOT_CLI_STATE_DIR
)

def scan_copilot_cli_sessions() -> list[dict]:
    results = []
    if not os.path.exists(COPILOT_CLI_STATE_DIR):
        return results
    
    try:
        subdirs = os.listdir(COPILOT_CLI_STATE_DIR)
    except Exception:
        return results
        
    for entry_name in subdirs:
        dir_path = os.path.join(COPILOT_CLI_STATE_DIR, entry_name)
        if not os.path.isdir(dir_path):
            continue
            
        events_path = os.path.join(dir_path, "events.jsonl")
        if not os.path.isfile(events_path):
            continue
            
        title = "Untitled Copilot CLI Session"
        mtime = os.path.getmtime(events_path)
        timestamp = int(mtime * 1000)
        
        try:
            with open(events_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        evt = json.loads(line)
                    except Exception:
                        continue
                        
                    evt_time = evt.get("timestamp") or evt.get("data", {}).get("timestamp")
                    if evt_time:
                        if isinstance(evt_time, (int, float)):
                            if evt_time < 1e11:
                                timestamp = int(evt_time * 1000)
                            else:
                                timestamp = int(evt_time)
                        elif isinstance(evt_time, str):
                            try:
                                from datetime import datetime
                                t_str = evt_time.replace("Z", "+00:00")
                                dt = datetime.fromisoformat(t_str)
                                timestamp = int(dt.timestamp() * 1000)
                            except Exception:
                                pass
                                
                    evt_type = evt.get("type") or evt.get("data", {}).get("type")
                    if evt_type == "user.message":
                        for key in ("message", "content", "text", "query"):
                            val = evt.get(key)
                            if not val and isinstance(evt.get("data"), dict):
                                val = evt["data"].get(key)
                            if val and isinstance(val, str):
                                title = val
                                break
                        break
        except Exception:
            pass
            
        if title:
            title = title.split("\n")[0].strip()
            if len(title) > 80:
                title = title[:77] + "..."
                
        if not title:
            title = "Untitled Copilot CLI Session"
            
        session_id = f"copilotcli:/{entry_name}"
        
        results.append({
            "session_id": session_id,
            "title": title,
            "time_created": timestamp,
            "source": "copilot",
            "jsonl_path": events_path,
            "workspace": "copilot-cli",
        })
        
    return results

def find_sessions_by_title(title_query: str) -> list[dict]:
    results = []
    seen_ids = set()
    seen_core_ids = set()
    query_lower = title_query.lower()

    for ws_dir in iter_workspace_dirs():
        entries = read_session_index(ws_dir)
        for sid, entry in entries.items():
            if sid in seen_ids or sid.startswith("claude-code:/"):
                continue
            
            core_id = sid
            if sid.startswith("copilotcli:/"):
                core_id = sid[len("copilotcli:/"):]
            seen_core_ids.add(core_id)

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

    cli_sessions = scan_copilot_cli_sessions()
    for sess in cli_sessions:
        sid = sess["session_id"]
        core_id = sid
        if sid.startswith("copilotcli:/"):
            core_id = sid[len("copilotcli:/"):]
            
        if core_id in seen_core_ids:
            continue
            
        if query_lower in sess["title"].lower() or query_lower in sid.lower():
            sess["jsonl_size"] = os.path.getsize(sess["jsonl_path"]) if sess["jsonl_path"] else 0
            results.append(sess)
            seen_core_ids.add(core_id)

    results.sort(key=lambda r: r["time_created"], reverse=True)
    return results

def list_recent_sessions(days: int = 2) -> list[dict]:
    cutoff = (time.time() - days * 86400) * 1000
    results = []
    seen_ids = set()
    seen_core_ids = set()

    for ws_dir in iter_workspace_dirs():
        entries = read_session_index(ws_dir)
        for sid, entry in entries.items():
            if sid in seen_ids or sid.startswith("claude-code:/"):
                continue
            
            core_id = sid
            if sid.startswith("copilotcli:/"):
                core_id = sid[len("copilotcli:/"):]
            seen_core_ids.add(core_id)

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

    cli_sessions = scan_copilot_cli_sessions()
    for sess in cli_sessions:
        sid = sess["session_id"]
        core_id = sid
        if sid.startswith("copilotcli:/"):
            core_id = sid[len("copilotcli:/"):]
            
        if core_id in seen_core_ids:
            continue
            
        if sess["time_created"] > cutoff:
            results.append(sess)
            seen_core_ids.add(core_id)

    results.sort(key=lambda r: r["time_created"], reverse=True)
    return results

def fetch_session_details(session: dict) -> dict:
    if not session.get("jsonl_path") or not os.path.exists(session["jsonl_path"]):
        session["turns"] = []
        return session
        
    parsed = parse_vscode_jsonl(session["jsonl_path"])
    session["turns"] = parsed.get("turns", [])
    return session
