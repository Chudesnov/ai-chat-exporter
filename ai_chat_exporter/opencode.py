import json
import os
import sqlite3
import sys
from datetime import datetime

OPENCODE_DB = os.path.expanduser("~/.local/share/opencode/opencode.db")

def get_db_connection():
    if not os.path.exists(OPENCODE_DB):
        print(f"Error: OpenCode database not found at {OPENCODE_DB}", file=sys.stderr)
        sys.exit(1)
    try:
        return sqlite3.connect(f"file:{OPENCODE_DB}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        return sqlite3.connect(OPENCODE_DB)

def list_recent_sessions(days: int = 7) -> list[dict]:
    conn = get_db_connection()
    cur = conn.cursor()
    cutoff = int((datetime.now().timestamp() - days * 86400) * 1000)
    
    cur.execute(
        "SELECT id, title, time_created, parent_id FROM session WHERE time_created >= ? ORDER BY time_created DESC",
        (cutoff,)
    )
    results = [
        {
            "session_id": row[0],
            "title": row[1] or "Untitled Session",
            "time_created": row[2],
            "parent_id": row[3],
            "source": "opencode",
        }
        for row in cur.fetchall()
    ]
    conn.close()
    return results

def find_sessions_by_title(query: str) -> list[dict]:
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute(
        "SELECT id, title, time_created, parent_id FROM session WHERE id = ? OR title LIKE ? ORDER BY time_created DESC",
        (query, f"%{query}%")
    )
    results = [
        {
            "session_id": row[0],
            "title": row[1] or "Untitled Session",
            "time_created": row[2],
            "parent_id": row[3],
            "source": "opencode",
        }
        for row in cur.fetchall()
    ]
    conn.close()
    return results

def get_related_sessions(session_id: str, parent_id: str | None) -> dict:
    conn = get_db_connection()
    cur = conn.cursor()
    
    related = {"parent": None, "children": []}
    
    if parent_id:
        cur.execute("SELECT id, title FROM session WHERE id = ?", (parent_id,))
        row = cur.fetchone()
        if row:
            related["parent"] = {"id": row[0], "title": row[1] or "Untitled Session"}
            
    cur.execute("SELECT id, title FROM session WHERE parent_id = ? ORDER BY time_created ASC", (session_id,))
    for row in cur.fetchall():
        related["children"].append({"id": row[0], "title": row[1] or "Untitled Session"})
        
    conn.close()
    return related

def get_session_turns(session_id: str) -> list[dict]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT m.data, p.data 
        FROM message m 
        JOIN part p ON m.id = p.message_id 
        WHERE m.session_id = ? 
        ORDER BY m.time_created ASC, p.time_created ASC
        """,
        (session_id,)
    )
    
    turns = []
    current_turn = None
    last_role = None
    
    for row in cur.fetchall():
        try:
            msg_data = json.loads(row[0])
            part_data = json.loads(row[1])
        except json.JSONDecodeError:
            continue
            
        role = msg_data.get("role", "unknown")
        
        if role == "user":
            if current_turn and current_turn["user"] and last_role != "user":
                turns.append(current_turn)
                current_turn = None
            
            if not current_turn:
                current_turn = {"user": [], "assistant": [], "tools": []}
                
            if part_data.get("type") == "text":
                text = part_data.get("text", "")
                if text.strip():
                    current_turn["user"].append(text)
                
        elif role == "assistant":
            if not current_turn:
                current_turn = {"user": [], "assistant": [], "tools": []}
                
            p_type = part_data.get("type")
            if p_type == "text":
                text = part_data.get("text", "")
                if text.strip():
                    current_turn["assistant"].append(text)
            elif p_type == "tool":
                tool_name = part_data.get("tool", "unknown")
                state = part_data.get("state", {})
                inputs = state.get("input", {})
                current_turn["tools"].append({
                    "name": tool_name,
                    "input": inputs
                })
        
        last_role = role
        
    if current_turn:
        turns.append(current_turn)
        
    conn.close()
    return turns

def fetch_session_details(session: dict) -> dict:
    """Hydrates the session dict with 'turns' and 'related'."""
    session["turns"] = get_session_turns(session["session_id"])
    session["related"] = get_related_sessions(session["session_id"], session.get("parent_id"))
    return session
