# mail-cli

A command-line interface for Apple Mail on macOS. Wraps AppleScript to provide fast, ergonomic email operations from the terminal.

## Features

- **List and search emails** with filters for subject, sender, date range, body content, and read status (all filters work with body search too)
- **Search across all folders** at once with `--all-folders`
- **Read messages** by index or message ID, in plain text, HTML, or extract links (with deduplication and plain-text URL fallback)
- **Delete and move** messages between folders, individually or in bulk
- **Manage folders**: create and delete mailbox folders
- **Send and reply** to emails from any configured account
- **Multiple accounts** with automatic inbox name normalization and date-sorted merged results
- **JSON output** for scripting and piping (pipe search results into bulk move/delete)

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
mail list                          # all accounts, sorted by date
mail list -a personal -n 10        # specific account, 10 messages
mail list -a work -f "Projects"    # specific folder (shows header)
mail list -A                       # all folders across all accounts
mail list -u                       # unread only
mail list -a work -u               # unread for one account
```

When listing from a specific folder, a header like `work/Projects (5)` is shown. When listing across accounts, results are merged and sorted by date.

### Search

```bash
mail search -s "invoice"                          # by subject
mail search --sender "alice@example.com"           # by sender
mail search --after 2025-01-01 --before 2025-02-01 # by date range
mail search -b "quarterly report" -a work          # body search (slower)
mail search -s "hotel" -A                          # search all folders
mail search -u --sender "boss@work.com"            # unread from a sender
mail search -u -b "action required"               # unread body search
```

Filters can be combined. Omit `--account` to search across all accounts. Use `-A` / `--all-folders` to search every folder instead of just the inbox.

### Read a message

```bash
mail read 1                             # read first message in inbox (by index)
mail read 3 -a work -f "Projects"       # read 3rd message in a specific folder
mail read <message-id>                  # read by message ID
mail read 1 --format html              # HTML body
mail read 1 --format links             # extract numbered links
mail read 1 --max-length 500           # truncate body
```

Indexes are 1-based, matching the order from `mail list`. Message IDs are shown in `list` and `search` output when using `--json`.

### Open in Mail.app

```bash
mail open 1                             # open first inbox message in Apple Mail
mail open 3 -a work -f "Projects"       # open by index in a folder
mail open <message-id>                  # open by message ID
```

### Open a link from an email

```bash
mail read 1 --format links              # see numbered links
mail open-link 1 2                       # open link [2] from message 1 in browser
mail open-link <message-id> 1            # open link [1] by message ID
```

### Delete

```bash
mail delete 1 -a personal                          # preview
mail delete 1 -a personal --confirm                # delete first message in inbox
mail delete 3 -a personal -f "ICLR" --confirm      # delete 3rd message in folder
mail delete <message-id> -a work --confirm         # delete by message ID
```

#### Bulk delete

```bash
mail delete -a personal --ids "id1,id2,id3" --confirm
mail search -s "newsletter" -a personal --json | mail delete -a personal --stdin --confirm
```

### Move

```bash
mail move 1 -a personal -t "Archive"                        # preview
mail move 1 -a personal -t "Archive" --confirm               # move from inbox to Archive
mail move 2 -a personal -f "ICLR" -t "INBOX" --confirm      # move between folders
```

#### Bulk move

```bash
mail move -a personal -t "Archive" --ids "id1,id2,id3" --confirm
mail search -s "receipts" -a personal --json | mail move -a personal -t "Receipts" --stdin --confirm
```

### Folder management

```bash
mail folder                        # list all folders (same as mail folders)
mail folder -a personal            # list folders for one account
mail folder create "Projects" -a work     # create a new folder
mail folder delete "Old Stuff" -a work    # preview deletion
mail folder delete "Old Stuff" -a work --confirm  # delete folder and all messages
```

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
mail account list         # show configured accounts
mail refresh              # check for new mail across all accounts
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

## Support

If you find this useful, [buy me a coffee](https://buymeacoffee.com/swanson).

<img src="assets/bmc_qr.png" alt="Buy Me a Coffee QR" width="200">
