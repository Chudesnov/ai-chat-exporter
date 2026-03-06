import json
import re

def sanitize_filename(title: str) -> str:
    """Convert a session title to a safe filename."""
    name = re.sub(r'[<>:"/\\|?*]', "", title)
    name = re.sub(r"\s+", " ", name).strip()
    if len(name) > 120:
        name = name[:120].rsplit(" ", 1)[0]
    return name

def format_tool_call(tool_name: str, tool_input: str | dict) -> list[str]:
    """Format a single tool call into a list of Markdown quote lines."""
    if isinstance(tool_input, dict):
        tool_input_str = json.dumps(tool_input, ensure_ascii=False)
    else:
        tool_input_str = str(tool_input)
        
    if len(tool_input_str) > 250:
        tool_input_str = tool_input_str[:247] + "..."
        
    tc_str = f"**{tool_name}**: `{tool_input_str}`"
    tc_lines = tc_str.split('\n')
    
    formatted = [f"> - {tc_lines[0]}"]
    for tcl in tc_lines[1:]:
        formatted.append(f">   {tcl}")
        
    return formatted
