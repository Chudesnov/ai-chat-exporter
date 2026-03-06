import json
import os
import re
import glob
from datetime import datetime

CLAUDE_PROJECTS_DIR = os.path.expanduser("~/.claude/projects")

def clean_user_text(text: str) -> str:
    text = re.sub(r'<ide_selection>.*?</ide_selection>', '', text, flags=re.DOTALL)
    text = re.sub(r'<ide_opened_file>.*?</ide_opened_file>', '', text, flags=re.DOTALL)
    text = re.sub(r'<local-command-caveat>.*?</local-command-caveat>', '', text, flags=re.DOTALL)
    text = re.sub(r'<command-name>.*?</command-name>', '', text, flags=re.DOTALL)
    text = re.sub(r'<command-message>.*?</command-message>', '', text, flags=re.DOTALL)
    text = re.sub(r'<command-args>.*?</command-args>', '', text, flags=re.DOTALL)
    text = re.sub(r'<local-command-stdout>.*?</local-command-stdout>', '', text, flags=re.DOTALL)
    
    text = re.sub(r'</?ide_selection>', '', text)
    text = re.sub(r'</?ide_opened_file>', '', text)
    text = re.sub(r'</?local-command-caveat>', '', text)
    return text.strip()

def extract_user_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for item in content:
            if item.get("type") == "text" and "text" in item:
                texts.append(item["text"])
        return "\n".join(texts)
    return ""

def _parse_jsonl_file(filepath: str) -> dict:
    turns = []
    current_turn = {"user": [], "assistant": [], "tools": []}
    
    first_user_msg = ""
    last_role = None
    session_id = os.path.basename(filepath).replace(".jsonl", "")
    created_ts = 0

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
                
            ts_str = data.get("timestamp")
            if ts_str:
                try:
                    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    ts = int(dt.timestamp() * 1000)
                    if created_ts == 0:
                        created_ts = ts
                except Exception:
                    pass

            msg_type = data.get("type")
            if msg_type not in ("user", "assistant"):
                continue
                
            msg = data.get("message", {})
            role = msg.get("role")

            if role == "user":
                content = msg.get("content", "")
                
                is_tool_result = False
                if isinstance(content, list):
                    if len(content) > 0 and content[0].get("type") == "tool_result":
                        is_tool_result = True
                
                if not is_tool_result:
                    if current_turn["user"] and last_role == "assistant":
                        turns.append(current_turn)
                        current_turn = {"user": [], "assistant": [], "tools": []}
                    
                    text = extract_user_content(content)
                    if text:
                        if data.get("isMeta"):
                            current_turn["user"].append(f"_Meta: {text}_")
                        else:
                            current_turn["user"].append(text)
                            
                        clean_text = clean_user_text(text)
                        if not first_user_msg and clean_text and not data.get("isMeta"):
                            first_user_msg = clean_text.split("\n")[0][:100]

            elif role == "assistant":
                content = msg.get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if item.get("type") == "text":
                            current_turn["assistant"].append(item.get("text", ""))
                        elif item.get("type") == "tool_use":
                            current_turn["tools"].append({
                                "name": item.get("name", "unknown"),
                                "input": item.get("input", {})
                            })
                            
            last_role = role

    if current_turn["user"] or current_turn["assistant"] or current_turn["tools"]:
        turns.append(current_turn)
        
    title = first_user_msg or "Untitled Claude Session"
    if len(title) > 80:
        title = title[:77] + "..."

    return {
        "session_id": session_id,
        "title": title,
        "time_created": created_ts,
        "source": "claude",
        "turns": turns,
        "jsonl_size": os.path.getsize(filepath),
        "jsonl_path": filepath
    }

def get_all_sessions() -> list[dict]:
    sessions = []
    if not os.path.exists(CLAUDE_PROJECTS_DIR):
        return sessions
        
    pattern = os.path.join(CLAUDE_PROJECTS_DIR, "*", "*.jsonl")
    for filepath in glob.glob(pattern):
        if os.path.getsize(filepath) < 100:
            continue
        try:
            s = _parse_jsonl_file(filepath)
            if s:
                if s["time_created"] == 0:
                    s["time_created"] = int(os.path.getctime(filepath) * 1000)
                sessions.append(s)
        except Exception:
            pass
    
    sessions.sort(key=lambda x: x["time_created"], reverse=True)
    return sessions

def list_recent_sessions(days: int = 7) -> list[dict]:
    cutoff = (datetime.now().timestamp() - days * 86400) * 1000
    sessions = get_all_sessions()
    return [s for s in sessions if s["time_created"] >= cutoff]

def find_sessions_by_title(query: str) -> list[dict]:
    sessions = get_all_sessions()
    query_lower = query.lower()
    return [s for s in sessions if query_lower in s["title"].lower() or query_lower in s["session_id"].lower()]

def fetch_session_details(session: dict) -> dict:
    """Claude parses everything upfront during finding sessions. We just return it."""
    # Ensure turns are loaded (they already are if generated by get_all_sessions)
    if "turns" not in session and "jsonl_path" in session:
        return _parse_jsonl_file(session["jsonl_path"])
    return session
