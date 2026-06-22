import json
import os
import glob
import sqlite3

VSCODE_STORAGE = os.path.expanduser("~/Library/Application Support/Code/User/workspaceStorage")
COPILOT_CLI_STATE_DIR = os.path.expanduser("~/.copilot/session-state")

def iter_workspace_dirs():
    for ws_dir in sorted(glob.glob(os.path.join(VSCODE_STORAGE, "*"))):
        if os.path.isfile(os.path.join(ws_dir, "state.vscdb")):
            yield ws_dir

def read_session_index(ws_dir: str) -> dict:
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

def find_vscode_jsonl(session_id: str) -> str | None:
    core_id = session_id
    if session_id.startswith("copilotcli:/"):
        core_id = session_id[len("copilotcli:/"):]
    cli_path = os.path.join(COPILOT_CLI_STATE_DIR, core_id, "events.jsonl")
    if os.path.isfile(cli_path):
        return cli_path

    for ws_dir in iter_workspace_dirs():
        entries = read_session_index(ws_dir)
        if session_id in entries:
            mapped_id = entries[session_id].get("sessionId", session_id)
            # The sessionId in the index might be the same as the session_id
            # but usually it doesn't have the protocol prefix in the filename
            mapped_id_clean = mapped_id.replace("copilotcli:/", "").replace("claude-code:/", "")
            
            path = os.path.join(ws_dir, "chatSessions", f"{mapped_id_clean}.jsonl")
            if os.path.isfile(path):
                return path
            
            path = os.path.join(ws_dir, "chatSessions", f"{mapped_id}.jsonl")
            if os.path.isfile(path):
                return path
            
        path = os.path.join(ws_dir, "chatSessions", f"{session_id}.jsonl")
        if os.path.isfile(path):
            return path
            
        clean_id = session_id.replace("copilotcli:/", "").replace("claude-code:/", "")
        path = os.path.join(ws_dir, "chatSessions", f"{clean_id}.jsonl")
        if os.path.isfile(path):
            return path
            
    return None

def apply_json_patch(target, path: list, value):
    """Recursively set a value in a nested dict/list at the given path."""
    if not path:
        return value
    
    current = target
    for i in range(len(path) - 1):
        key = path[i]
        # if the next key is an int, make sure current[key] is a list or pad it
        next_key = path[i+1]
        
        if isinstance(current, dict):
            if key not in current:
                current[key] = [] if isinstance(next_key, int) else {}
            current = current[key]
        elif isinstance(current, list):
            while len(current) <= key:
                current.append(None)
            if current[key] is None:
                current[key] = [] if isinstance(next_key, int) else {}
            current = current[key]

    key = path[-1]
    if isinstance(current, dict):
        current[key] = value
    elif isinstance(current, list):
        while len(current) <= key:
            current.append(None)
        current[key] = value

def append_json_patch(target, path: list, values: list):
    """Recursively append elements to a list in a nested dict/list at the given path."""
    current = target
    for i in range(len(path)):
        key = path[i]
        is_last = (i == len(path) - 1)
        
        if isinstance(current, dict):
            if is_last:
                if key not in current or not isinstance(current[key], list):
                    current[key] = []
                current[key].extend(values)
            else:
                next_key = path[i+1]
                if key not in current:
                    current[key] = [] if isinstance(next_key, int) else {}
                current = current[key]
                
        elif isinstance(current, list):
            while len(current) <= key:
                current.append(None)
            if is_last:
                if current[key] is None:
                    current[key] = []
                if isinstance(current[key], list):
                    current[key].extend(values)
            else:
                next_key = path[i+1]
                if current[key] is None:
                    current[key] = [] if isinstance(next_key, int) else {}
                current = current[key]

def parse_copilot_cli_jsonl(filepath: str) -> dict:
    def extract_message_text(evt) -> str | None:
        for key in ("message", "content", "text", "query"):
            val = evt.get(key)
            if val and isinstance(val, str):
                return val
        data = evt.get("data")
        if isinstance(data, dict):
            for key in ("message", "content", "text", "query"):
                val = data.get(key)
                if val and isinstance(val, str):
                    return val
        return None

    def extract_assistant_text(evt) -> str | None:
        for key in ("message", "content", "text", "response"):
            val = evt.get(key)
            if val and isinstance(val, str):
                return val
        data = evt.get("data")
        if isinstance(data, dict):
            for key in ("message", "content", "text", "response"):
                val = data.get(key)
                if val and isinstance(val, str):
                    return val
        return None

    turns = []
    current_turn = None
    
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            evt_type = evt.get("type")
            if not evt_type and "data" in evt:
                data = evt.get("data")
                if isinstance(data, dict):
                    evt_type = data.get("type")
            
            if evt_type == "user.message":
                if current_turn is not None:
                    if current_turn["user"] or current_turn["assistant"] or current_turn["tools"]:
                        turns.append(current_turn)
                current_turn = {"user": [], "assistant": [], "tools": []}
                
                text = extract_message_text(evt)
                if text:
                    current_turn["user"].append(text)
                    
            elif evt_type == "assistant.message":
                if current_turn is None:
                    current_turn = {"user": [], "assistant": [], "tools": []}
                
                text = extract_assistant_text(evt)
                if text:
                    current_turn["assistant"].append(text)
            
            # Extract tool requests if present on any event
            tool_reqs = evt.get("toolRequests")
            if not tool_reqs and isinstance(evt.get("data"), dict):
                tool_reqs = evt["data"].get("toolRequests")
            
            if isinstance(tool_reqs, list):
                if current_turn is None:
                    current_turn = {"user": [], "assistant": [], "tools": []}
                for tr in tool_reqs:
                    if not isinstance(tr, dict):
                        continue
                    name = tr.get("name") or tr.get("tool") or tr.get("toolName") or "unknown"
                    args = tr.get("arguments") or tr.get("input") or tr.get("args") or tr.get("parameters") or {}
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except:
                            args = {"raw": args}
                    if not isinstance(args, dict):
                        args = {"value": args}
                    
                    current_turn["tools"].append({
                        "name": name,
                        "input": args
                    })
                    
    if current_turn is not None:
        if current_turn["user"] or current_turn["assistant"] or current_turn["tools"]:
            turns.append(current_turn)
            
    # Deduplicate tools
    for turn in turns:
        seen = set()
        deduped_tools = []
        for t in turn["tools"]:
            k = f"{t['name']}|{str(t['input'])}"
            if k not in seen:
                seen.add(k)
                deduped_tools.append(t)
        turn["tools"] = deduped_tools
        
    return {"turns": turns}

def parse_vscode_jsonl(filepath: str) -> dict:
    # Check if this file is a Copilot CLI event stream
    is_cli = False
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                evt = json.loads(line)
                if isinstance(evt, dict):
                    if "type" in evt or "timestamp" in evt or ("data" in evt and not "kind" in evt):
                        is_cli = True
                break
    except Exception:
        pass

    if is_cli:
        return parse_copilot_cli_jsonl(filepath)

    state = {}
    
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
                
            kind = evt.get("kind")
            v = evt.get("v")
            k = evt.get("k")
            
            if kind == 0:
                state = v
            elif kind == 1 and k:
                apply_json_patch(state, k, v)
            elif kind == 2 and k and isinstance(v, list):
                append_json_patch(state, k, v)

    turns = []
    requests = state.get("requests", [])
    
    for req in requests:
        if not req:
            continue
            
        turn = {"user": [], "assistant": [], "tools": []}
        
        # User message
        msg = req.get("message", {})
        if "text" in msg and msg["text"]:
            turn["user"].append(msg["text"])
            
        # Assistant response chunks
        response_chunks = req.get("response", [])
        text_buf = []
        
        for chunk in response_chunks:
            if not isinstance(chunk, dict):
                continue
                
            chunk_kind = chunk.get("kind")
            
            # Text chunk
            if "value" in chunk and chunk_kind not in ("thinking", "toolInvocationSerialized"):
                text_buf.append(chunk["value"])
                
            # Direct tool invocation inline
            if chunk_kind == "toolInvocationSerialized":
                tool_id = chunk.get("toolId", "unknown")
                inv_obj = chunk.get("invocationMessage", {})
                if isinstance(inv_obj, str):
                    inv_msg = inv_obj
                else:
                    inv_msg = inv_obj.get("value", tool_id)
                turn["tools"].append({"name": inv_msg, "input": {}})

        if text_buf:
            turn["assistant"].append("".join(text_buf).strip())

        # Tool calls from metadata
        metadata = req.get("result", {}).get("metadata", {})
        tool_call_rounds = metadata.get("toolCallRounds", [])
        
        for round_item in tool_call_rounds:
            for tc in round_item.get("toolCalls", []):
                args = tc.get("arguments", "{}")
                try:
                    args_dict = json.loads(args)
                except:
                    args_dict = {"raw": args}
                turn["tools"].append({
                    "name": tc.get("name", "unknown"),
                    "input": args_dict
                })
                
        # Deduplicate tools
        seen = set()
        deduped_tools = []
        for t in turn["tools"]:
            k = f"{t['name']}|{str(t['input'])}"
            if k not in seen:
                seen.add(k)
                deduped_tools.append(t)
        turn["tools"] = deduped_tools
        
        turns.append(turn)

    return {"turns": turns}
