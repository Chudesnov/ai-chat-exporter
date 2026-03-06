import json
from datetime import datetime

from .utils import sanitize_filename, format_tool_call

def render_markdown(session: dict) -> str:
    """Render a parsed session dict into an Obsidian-compatible Markdown string."""
    title = session.get("title", "Untitled Session")
    session_id = session.get("session_id", "unknown")
    time_created = session.get("time_created", 0)
    source = session.get("source", "unknown")
    turns = session.get("turns", [])
    related = session.get("related", {})
    
    tag_map = {
        "opencode": "opencode-chat",
        "copilot": "copilot-chat",
        "claude": "claude-chat"
    }
    tag = tag_map.get(source, "ai-chat")

    lines = []
    lines.append("---")
    lines.append(f'title: "{title}"')
    lines.append(f'session_id: "{session_id}"')
    if time_created:
        dt = datetime.fromtimestamp(time_created / 1000)
        lines.append(f"date: {dt.strftime('%Y-%m-%d')}")
        lines.append(f"created: {dt.strftime('%Y-%m-%dT%H:%M:%S')}")
    lines.append(f"turns: {len(turns)}")
    lines.append(f"tags: [{tag}]")
    lines.append("---")
    lines.append("")
    lines.append(f"# {title}")
    lines.append("")

    if related.get("parent"):
        parent_title = related["parent"]["title"]
        safe_parent = sanitize_filename(parent_title)
        lines.append(f"**Parent Session:** [[{safe_parent}]]")
        lines.append("")
        
    if related.get("children"):
        lines.append("**Subagents (Child Sessions):**")
        for child in related["children"]:
            safe_child = sanitize_filename(child["title"])
            lines.append(f"- [[{safe_child}]]")
        lines.append("")

    for idx, turn in enumerate(turns):
        lines.append(f"## Turn {idx + 1}")
        lines.append("")
        
        user_texts = turn.get("user", [])
        if user_texts:
            lines.append("### User")
            lines.append("")
            for text in user_texts:
                lines.append(str(text))
                lines.append("")

        tools = turn.get("tools", [])
        if tools:
            lines.append(f"> [!info]- Tool Calls ({len(tools)})")
            lines.append("> ")
            for tc in tools:
                lines.extend(format_tool_call(tc["name"], tc.get("input", tc.get("args", ""))))
            lines.append("")

        assistant_texts = turn.get("assistant", [])
        if assistant_texts:
            lines.append("### Assistant")
            lines.append("")
            for text in assistant_texts:
                lines.append(str(text))
                lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)
