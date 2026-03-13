# email-cli

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
email account init
```

This creates `~/.config/email-cli/accounts.json` with your account names, inbox folder names, and email addresses. You can also edit this file directly:

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
email list                          # all accounts, sorted by date
email list -a personal -n 10        # specific account, 10 messages
email list -a work -f "Projects"    # specific folder (shows header)
email list -A                       # all folders across all accounts
email list -u                       # unread only
email list -a work -u               # unread for one account
```

When listing from a specific folder, a header like `work/Projects (5)` is shown. When listing across accounts, results are merged and sorted by date.

### Search

```bash
email search -s "invoice"                          # by subject
email search --sender "alice@example.com"           # by sender
email search --after 2025-01-01 --before 2025-02-01 # by date range
email search -b "quarterly report" -a work          # body search (slower)
email search -s "hotel" -A                          # search all folders
email search -u --sender "boss@work.com"            # unread from a sender
email search -u -b "action required"               # unread body search
```

Filters can be combined. Omit `--account` to search across all accounts. Use `-A` / `--all-folders` to search every folder instead of just the inbox.

### Read a message

```bash
email read 1                             # read first message in inbox (by index)
email read 3 -a work -f "Projects"       # read 3rd message in a specific folder
email read <message-id>                  # read by message ID
email read 1 --format html              # HTML body
email read 1 --format links             # extract numbered links
email read 1 --max-length 500           # truncate body
```

Indexes are 1-based, matching the order from `email list`. Message IDs are shown in `list` and `search` output when using `--json`.

### Open in Mail.app

```bash
email open 1                             # open first inbox message in Apple Mail
email open 3 -a work -f "Projects"       # open by index in a folder
email open <message-id>                  # open by message ID
```

### Open a link from an email

```bash
email read 1 --format links              # see numbered links
email open-link 1 2                       # open link [2] from message 1 in browser
email open-link <message-id> 1            # open link [1] by message ID
```

### Delete

```bash
email delete 1 -a personal                          # preview
email delete 1 -a personal --confirm                # delete first message in inbox
email delete 3 -a personal -f "ICLR" --confirm      # delete 3rd message in folder
email delete <message-id> -a work --confirm         # delete by message ID
```

#### Bulk delete

```bash
email delete -a personal --ids "id1,id2,id3" --confirm
email search -s "newsletter" -a personal --json | email delete -a personal --stdin --confirm
```

### Move

```bash
email move 1 -a personal -t "Archive"                        # preview
email move 1 -a personal -t "Archive" --confirm               # move from inbox to Archive
email move 2 -a personal -f "ICLR" -t "INBOX" --confirm      # move between folders
```

#### Bulk move

```bash
email move -a personal -t "Archive" --ids "id1,id2,id3" --confirm
email search -s "receipts" -a personal --json | email move -a personal -t "Receipts" --stdin --confirm
```

### Folder management

```bash
email folder                        # list all folders (same as email folders)
email folder -a personal            # list folders for one account
email folder create "Projects" -a work     # create a new folder
email folder delete "Old Stuff" -a work    # preview deletion
email folder delete "Old Stuff" -a work --confirm  # delete folder and all messages
```

### Send

```bash
email send -a work --to alice@example.com -s "Hello" -b "Message body"           # preview
email send -a work --to alice@example.com -s "Hello" -b "Message body" --confirm  # send
```

### Reply

```bash
email reply <message-id> -b "Thanks!" --confirm
email reply <message-id> -b "Thanks!" --all --confirm  # reply all
```

### Other

```bash
email account list         # show configured accounts
email refresh              # check for new mail across all accounts
```

### JSON output

All list/search/read commands support `--json` for structured output:

```bash
email list -a work --json | jq '.[0].subject'
```

## How it works

email-cli generates AppleScript, executes it via `osascript`, and parses the output in Python. Body search fetches message content in batches and filters in Python, since AppleScript's `whose` clause can't search message bodies.

## Limitations

- macOS only (requires Apple Mail)
- Body search is slower than metadata search since it fetches content for each candidate message
- Apple Mail must be running (AppleScript launches it automatically if needed)

## Support

If you find this useful, [buy me a coffee](https://buymeacoffee.com/swanson).

<img src="assets/bmc_qr.png" alt="Buy Me a Coffee QR" width="200">
