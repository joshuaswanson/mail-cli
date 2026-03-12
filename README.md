# mail-cli

A command-line interface for Apple Mail on macOS. Wraps AppleScript to provide fast, ergonomic email operations from the terminal.

## Features

- **List and search emails** with filters for subject, sender, date range, and body content
- **Read messages** in plain text, HTML, or extract links
- **Send and reply** to emails from any configured account
- **Multiple accounts** with automatic inbox name normalization
- **JSON output** for scripting and piping

## Installation

Requires Python 3.11+ and macOS with Apple Mail configured.

```bash
uv venv && uv pip install -e .
```

## Setup

Configure your mail accounts:

```bash
mail account init
```

This creates `~/.config/mail-cli/accounts.json` with your account names, inbox folder names, and email addresses. You can also edit this file directly:

```json
{
  "personal": {
    "name": "iCloud",
    "inbox": "INBOX",
    "email": "you@icloud.com"
  },
  "work": {
    "name": "Work Account",
    "inbox": "Inbox",
    "email": "you@work.com"
  }
}
```

Note: different mail providers use different inbox names (e.g. iCloud uses `INBOX`, Exchange uses `Inbox`). The config handles this automatically.

## Usage

### List recent messages

```bash
mail list                          # all accounts, 20 most recent
mail list -a personal -n 10        # specific account, 10 messages
mail list -a work -f "Projects"    # specific folder
```

### Search

```bash
mail search -s "invoice"                          # by subject
mail search --sender "alice@example.com"           # by sender
mail search --after 2025-01-01 --before 2025-02-01 # by date range
mail search -b "quarterly report" -a work          # body search (slower)
```

Filters can be combined. Omit `--account` to search across all accounts.

### Read a message

```bash
mail read <message-id>                  # plain text
mail read <message-id> --format html    # HTML body
mail read <message-id> --format links   # extract all links
mail read <message-id> --max-length 500 # truncate body
```

Message IDs are shown in `list` and `search` output when using `--json`.

### Send

```bash
mail send -a work --to alice@example.com -s "Hello" -b "Message body"           # preview
mail send -a work --to alice@example.com -s "Hello" -b "Message body" --confirm  # send
```

### Reply

```bash
mail reply <message-id> -b "Thanks!" --confirm
mail reply <message-id> -b "Thanks!" --all --confirm  # reply all
```

### Other

```bash
mail folders              # list all folders for all accounts
mail folders -a personal  # list folders for one account
mail account list         # show configured accounts
```

### JSON output

All list/search/read commands support `--json` for structured output:

```bash
mail list -a work --json | jq '.[0].subject'
```

## How it works

mail-cli generates AppleScript, executes it via `osascript`, and parses the output in Python. Body search fetches message content in batches and filters in Python, since AppleScript's `whose` clause can't search message bodies.

## Limitations

- macOS only (requires Apple Mail)
- Body search is slower than metadata search since it fetches content for each candidate message
- Apple Mail must be running (AppleScript launches it automatically if needed)
