import json
import os
import glob
import sqlite3
import time

VSCODE_STORAGE = os.path.expanduser("~/Library/Application Support/Code/User/workspaceStorage")

def _iter_workspace_dirs():
    for ws_dir in sorted(glob.glob(os.path.join(VSCODE_STORAGE, "*"))):
        if os.path.isfile(os.path.join(ws_dir, "state.vscdb")):
            yield ws_dir

def _read_session_index(ws_dir: str) -> dict:
    db = os.path.join(ws_dir, "state.vscdb")
    try:
        conn = sqlite3.connect(db)
        row = conn.execute("SELECT value FROM ItemTable WHERE key = 'chat.ChatSessionStore.index'").fetchone()
        conn.close()
        if row:
            return json.loads(row[0]).get("entries", {})
    except Exception:
        pass
    return {}

def _find_jsonl(session_id: str) -> str | None:
    for ws_dir in _iter_workspace_dirs():
        path = os.path.join(ws_dir, "chatSessions", f"{session_id}.jsonl")
        if os.path.isfile(path):
            return path
    return None

def find_sessions_by_title(title_query: str) -> list[dict]:
    results = []
    seen_ids = set()
    query_lower = title_query.lower()

    for ws_dir in _iter_workspace_dirs():
        entries = _read_session_index(ws_dir)
        for sid, entry in entries.items():
            if sid in seen_ids:
                continue
            session_title = entry.get("title", "")
            if query_lower in session_title.lower() or query_lower in sid.lower():
                jsonl = _find_jsonl(sid)
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

    for ws_dir in _iter_workspace_dirs():
        entries = _read_session_index(ws_dir)
        for sid, entry in entries.items():
            if sid in seen_ids:
                continue
            ts = entry.get("lastMessageDate", 0)
            if ts > cutoff and not entry.get("isEmpty", True):
                results.append({
                    "session_id": sid,
                    "title": entry.get("title", "New Chat"),
                    "time_created": ts,
                    "source": "copilot",
                    "jsonl_path": _find_jsonl(sid),
                    "workspace": os.path.basename(ws_dir),
                })
                seen_ids.add(sid)

    results.sort(key=lambda r: r["time_created"], reverse=True)
    return results

def _load_jsonl(path: str) -> list[dict]:
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            entries.append(json.loads(line))
    return entries

def _is_reqid_entry(entry: dict) -> bool:
    if entry.get("kind") != 2: return False
    v = entry.get("v")
    if not isinstance(v, list): return False
    return any(isinstance(i, dict) and "requestId" in i for i in v[:3])

def _is_completion_marker(entry: dict) -> bool:
    if entry.get("kind") != 1: return False
    v = entry.get("v")
    return isinstance(v, dict) and "completedAt" in v

def _extract_text_from_response_list(items: list) -> tuple[list[str], list[str]]:
    texts = []
    tools = []
    inline_buf: list[str] = []

    def _flush_inline():
        if not inline_buf: return
        merged = "".join(inline_buf)
        if merged.strip(): texts.append(merged)
        inline_buf.clear()

    for item in items:
        if not isinstance(item, dict): continue
        if "requestId" in item: continue

        inv = item.get("invocationMessage", "")
        past = item.get("pastTenseMessage", "")
        if (inv or past) and "supportHtml" not in item:
            _flush_inline()
            if "value" in item:
                val = item["value"]
                if isinstance(val, str) and val.strip():
                    texts.append(val.strip())
            else:
                tool_label = past or inv
                if isinstance(tool_label, str) and tool_label.strip():
                    tools.append(tool_label.strip())
                elif isinstance(tool_label, dict):
                    tv = tool_label.get("value", "")
                    if isinstance(tv, str) and tv.strip():
                        tools.append(tv.strip())
            continue

        if "inlineReference" in item and "supportHtml" not in item:
            ref = item.get("inlineReference", {})
            if isinstance(ref, dict):
                name = ref.get("name", "")
                path = ref.get("path", "")
                display = name or (path.split("/")[-1] if path else "")
                if display: inline_buf.append(f"`{display}`")
            continue

        if "supportHtml" in item:
            val = item.get("value", "")
            if isinstance(val, str): inline_buf.append(val)
            continue

        val = item.get("value", "")
        if isinstance(val, str) and val.strip():
            _flush_inline()
            texts.append(val)

    _flush_inline()
    return texts, tools

def parse_session(entries: list[dict], existing_title: str) -> dict:
    if not entries: return {"turns": []}

    reqid_indices = [i for i, e in enumerate(entries) if _is_reqid_entry(e)]
    completion_indices = [i for i, e in enumerate(entries) if _is_completion_marker(e)]

    if not reqid_indices: return {"turns": []}

    turn_groups = []
    current_group = [reqid_indices[0]]

    for k in range(1, len(reqid_indices)):
        prev_ri = reqid_indices[k - 1]
        curr_ri = reqid_indices[k]
        has_new_user_msg = False
        for j in range(prev_ri + 1, curr_ri):
            e = entries[j]
            if e.get("kind") == 1 and isinstance(e.get("v"), str) and len(e["v"].strip()) > 15:
                v = e["v"].strip()
                if v not in ("GitHub Copilot", "") and v != existing_title:
                    has_new_user_msg = True
                    break
        if has_new_user_msg:
            turn_groups.append(current_group)
            current_group = [curr_ri]
        else:
            current_group.append(curr_ri)
    turn_groups.append(current_group)

    turns = []
    for gi, group in enumerate(turn_groups):
        first_reqid = group[0]
        last_reqid = group[-1]

        prev_boundary = 0
        for ci in reversed(completion_indices):
            if ci < first_reqid:
                prev_boundary = ci + 1
                break

        user_msg = ""
        user_msg_len = 0
        for j in range(prev_boundary, first_reqid):
            e = entries[j]
            if e.get("kind") == 1 and isinstance(e.get("v"), str):
                v = e["v"].strip()
                if not v or v == "GitHub Copilot": continue
                if len(v) > user_msg_len:
                    if user_msg and len(v) < len(user_msg): pass
                    else:
                        user_msg = v
                        user_msg_len = len(v)

        turn_end = len(entries)
        if gi + 1 < len(turn_groups):
            turn_end = turn_groups[gi + 1][0]
        else:
            for ci in completion_indices:
                if ci > last_reqid:
                    turn_end = ci + 1
                    break

        while turn_end < len(entries):
            e = entries[turn_end]
            if e.get("kind") == 2 and isinstance(e.get("v"), list): turn_end += 1
            else: break

        all_items = []
        for j in range(first_reqid, turn_end):
            e = entries[j]
            v = e.get("v")
            if isinstance(v, list) and len(v) > 0:
                all_items.extend(v)

        all_texts, all_tools = _extract_text_from_response_list(all_items)

        deduped_texts = []
        prev = None
        for t in all_texts:
            t_clean = t.strip()
            if t_clean and t_clean != prev:
                deduped_texts.append(t_clean)
                prev = t_clean

        # Deduplicate tool calls
        deduped_tools = []
        seen_tools = set()
        for tc in all_tools:
            if tc not in seen_tools:
                deduped_tools.append({"name": tc, "input": ""})
                seen_tools.add(tc)

        turns.append(
            {
                "user": [user_msg] if user_msg else [],
                "assistant": deduped_texts,
                "tools": deduped_tools,
            }
        )

    return {"turns": turns}

def fetch_session_details(session: dict) -> dict:
    if not session.get("jsonl_path") or not os.path.exists(session["jsonl_path"]):
        session["turns"] = []
        return session
        
    entries = _load_jsonl(session["jsonl_path"])
    parsed = parse_session(entries, session.get("title", ""))
    session["turns"] = parsed.get("turns", [])
    return session
