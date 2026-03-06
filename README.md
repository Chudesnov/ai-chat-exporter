# AI Chat Exporter 🤖📝

A unified command-line tool to extract and export AI chat sessions from multiple development environments into clean, Obsidian-ready Markdown files. 

Stop losing your development context! This tool aggregates your past interactions, formats tool calls cleanly in collapsible callouts, links parent and subagent sessions together, and structures the output beautifully.

## Supported Platforms

* **[OpenCode](https://opencode.ai/)** (`[OP]`)
* **VSCode GitHub Copilot** (`[CO]`)
* **Claude Code (CLI & VSCode Extension)** (`[CL]`)

## Installation

You can install the package directly via `pip` or `pipx`:

```bash
# Clone the repository
git clone https://github.com/Chudesnov/ai-chat-exporter.git
cd ai-chat-exporter

# Install globally or in an editable way
pip install -e .
# OR
pipx install .
```

## Usage

Once installed, the `ai-chat-export` command is available globally.

### List Recent Sessions
List your chat history from the last 7 days (default) across all platforms:
```bash
ai-chat-export --list
```
*Output will clearly label each source with `[OP]`, `[CO]`, or `[CL]` tags.*

### Search & Export
Pass a partial title, ID, or query to find a session and export it:
```bash
ai-chat-export "card sort"
```
If multiple sessions match, you'll be prompted to choose which one to export, or you can use the `--all` flag to export every match.

### Options
```text
  title                 Session title or ID (partial match)
  --source, -s          Which exporter to use (choices: all, opencode, copilot, claude)
  --output, -o          Output file path (overrides Obsidian directory)
  --all, -a             Export all matches
  --list, -l            List recent sessions
  --days, -d            Days to look back (default: 7)
```

## Storage Defaults

By default, the tool outputs your `.md` files to:
`~/Notes/Main/OpenCode Chat Archive/`, `~/Notes/Main/Copilot Chat Archive/`, or `~/Notes/Main/Claude Chat Archive/` depending on the source.

You can override the base directory globally by setting the `OBSIDIAN_DIR` environment variable, or on a per-command basis using the `--output` flag.

## Credits

Built dynamically, iteratively, and cooperatively by **Sasha** and **OpenCode** (powered by Google's **Gemini 3.1 Pro Preview**) working side-by-side in real time! ✨
