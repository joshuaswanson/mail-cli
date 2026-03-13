"""CLI entry point for mail-cli."""

import json
import logging
import sys
from datetime import datetime as _datetime

import click

from . import accounts, applescript

logger = logging.getLogger(__name__)

DIM = "bright_black"
SENDER = "cyan"
UNREAD = "white"


def _truncate(text: str, length: int = 80) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) > length:
        return text[:length - 3] + "..."
    return text


def _format_msg(m: dict, show_account: bool = False, show_folder: bool = False) -> str:
    read_marker = " " if m["read"] else click.style("*", fg="yellow")
    date = click.style(m["date"], fg=DIM)
    sender = click.style(_truncate(m["sender"], 30), fg=SENDER)
    subject = m["subject"]
    parts = [read_marker, date, " ", sender, "  ", subject]
    tags = []
    if show_account:
        tags.append(m["account"])
    if show_folder:
        tags.append(m["folder"])
    if tags:
        parts.append("  " + click.style(f'[{"/".join(tags)}]', fg=DIM))
    return "".join(parts)


def _parse_date(date_str: str) -> _datetime:
    """Best-effort parse of AppleScript date strings for sorting."""
    for fmt in (
        "%A, %B %d, %Y at %H:%M:%S",
        "%A, %B %d, %Y at %I:%M:%S %p",
        "%B %d, %Y at %H:%M:%S",
        "%B %d, %Y at %I:%M:%S %p",
        "%d %B %Y at %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d.%m.%Y %H:%M:%S",
    ):
        try:
            return _datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    logger.warning("Could not parse date: %r", date_str)
    return _datetime.min


def _sort_by_date(msgs: list[dict]) -> list[dict]:
    """Sort messages by date, newest first."""
    return sorted(msgs, key=lambda m: _parse_date(m.get("date", "")), reverse=True)


def _print_header(alias: str, folder: str, count: int) -> None:
    label = click.style(f"{alias}/{folder}", bold=True)
    count_str = click.style(f"({count})", fg=DIM)
    click.echo(f"{label} {count_str}")


def _resolve_msg_id(identifier: str, account_name: str, folder: str) -> str | None:
    """Resolve an identifier (index or message ID) to a message ID."""
    try:
        idx = int(identifier)
        msgs = applescript.list_messages(account_name, folder, limit=idx)
        if idx < 1 or idx > len(msgs):
            return None
        return msgs[idx - 1]["message_id"]
    except ValueError:
        return identifier


def _read_ids_from_stdin() -> list[str]:
    """Read message IDs from stdin (one per line, or JSON array)."""
    if sys.stdin.isatty():
        return []
    raw = sys.stdin.read().strip()
    if not raw:
        return []
    # Try JSON array first (from --json piping)
    if raw.startswith("["):
        try:
            data = json.loads(raw)
            return [m["message_id"] for m in data if "message_id" in m]
        except (json.JSONDecodeError, TypeError):
            pass
    # Fall back to one ID per line
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _resolve_targets(acct: str | None, folder: str | None, all_folders: bool):
    """Return list of (alias, config, mailbox) tuples to search."""
    if all_folders:
        targets = []
        acct_list = [(acct, accounts.resolve_account(acct))] if acct else accounts.all_accounts()
        for alias, config in acct_list:
            for f in applescript.list_folders(config["name"]):
                targets.append((alias, config, f))
        return targets

    acct_list = [(acct, accounts.resolve_account(acct))] if acct else accounts.all_accounts()
    return [(alias, config, accounts.resolve_folder(alias, folder)) for alias, config in acct_list]


@click.group()
def cli():
    """CLI for Apple Mail."""


# --- accounts ---


@cli.command("refresh")
def refresh_cmd():
    """Check for new mail across all accounts."""
    applescript.check_for_new_mail()
    click.echo("Checking for new mail...")


@cli.group()
def account():
    """Manage mail accounts."""


@account.command("init")
def account_init():
    """Interactive setup for mail accounts."""
    config = {}
    click.echo("Add mail accounts. Enter an empty alias to finish.\n")
    while True:
        alias = click.prompt("Account alias (e.g. icloud, eth)", default="", show_default=False)
        if not alias:
            break
        name = click.prompt("  Account name in Apple Mail (e.g. iCloud, ETH Zurich)")
        inbox = click.prompt("  Inbox mailbox name", default="INBOX")
        email = click.prompt("  Email address")
        config[alias.lower()] = {"name": name, "inbox": inbox, "email": email}
        click.echo()
    if config:
        accounts.save(config)
        click.echo(f"Saved {len(config)} account(s) to {accounts.CONFIG_FILE}")
    else:
        click.echo("No accounts configured.")


@account.command("list")
def account_list():
    """Show configured accounts."""
    for alias, acct in accounts.all_accounts():
        click.echo(f'{click.style(alias, bold=True)}  {acct["name"]}  {acct["email"]}  inbox={acct["inbox"]}')


# --- folders ---


@cli.group("folder", invoke_without_command=True)
@click.option("--account", "-a", "acct", default=None, help="Account alias.")
@click.pass_context
def folder_group(ctx, acct: str | None):
    """Manage mailbox folders. Lists folders when called without a subcommand."""
    ctx.ensure_object(dict)
    ctx.obj["acct"] = acct
    if ctx.invoked_subcommand is None:
        targets = [(acct, accounts.resolve_account(acct))] if acct else accounts.all_accounts()
        for alias, config in targets:
            folders = applescript.list_folders(config["name"])
            label = click.style(alias, bold=True)
            click.echo(f"{label}: {', '.join(folders)}")


cli.add_command(folder_group, "folders")


@folder_group.command("create")
@click.argument("name")
@click.option("--account", "-a", "acct", required=True, help="Account alias.")
def folder_create(name, acct):
    """Create a new mailbox folder."""
    config = accounts.resolve_account(acct)
    result = applescript.create_folder(config["name"], name)
    if result == "already exists":
        click.echo(f"Folder {name!r} already exists in {acct}.")
    else:
        click.echo(f"Created folder {name!r} in {acct}.")


@folder_group.command("delete")
@click.argument("name")
@click.option("--account", "-a", "acct", required=True, help="Account alias.")
@click.option("--confirm", is_flag=True, help="Actually delete (required).")
def folder_delete(name, acct, confirm):
    """Delete a mailbox folder and all its messages."""
    config = accounts.resolve_account(acct)
    if not confirm:
        try:
            msgs = applescript.list_messages(config["name"], name, limit=500)
            count = len(msgs)
        except RuntimeError:
            count = 0
        click.echo(f'{click.style("Delete folder:", bold=True)} {name} ({count} messages)')
        click.echo(f'{click.style("Account:", bold=True)} {acct}')
        click.echo(f'\nPass {click.style("--confirm", bold=True)} to actually delete.')
        return
    result = applescript.delete_folder(config["name"], name)
    click.echo(f"Deleted folder {name!r} from {acct}.")


# --- list ---


@cli.command("list")
@click.option("--account", "-a", "acct", default=None, help="Account alias.")
@click.option("--folder", "-f", default=None, help="Mailbox folder (default: inbox).")
@click.option("--all-folders", "-A", is_flag=True, help="Search all folders.")
@click.option("--unread", "-u", is_flag=True, help="Show only unread messages.")
@click.option("--limit", "-n", default=20, help="Number of messages.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def list_cmd(acct: str | None, folder: str | None, all_folders: bool, unread: bool, limit: int, as_json: bool):
    """List recent messages."""
    targets = _resolve_targets(acct, folder, all_folders)
    all_msgs = []
    for alias, config, mailbox in targets:
        try:
            msgs = applescript.list_messages(config["name"], mailbox, limit=limit, unread_only=unread)
            all_msgs.extend(msgs)
        except RuntimeError as e:
            logger.warning("Error listing %s/%s: %s", alias, mailbox, e)
            continue

    all_msgs = _sort_by_date(all_msgs)

    if as_json:
        click.echo(json.dumps(all_msgs, indent=2))
        return

    if not all_msgs:
        click.echo("No messages found.")
        return

    show_account = acct is None
    multi_source = all_folders or (acct is None)
    if not multi_source and folder:
        _print_header(acct or targets[0][0], folder, len(all_msgs))
    for m in all_msgs:
        click.echo(_format_msg(m, show_account, show_folder=all_folders))


# --- search ---


@cli.command("search")
@click.option("--account", "-a", "acct", default=None, help="Account alias.")
@click.option("--folder", "-f", default=None, help="Mailbox folder (default: inbox).")
@click.option("--all-folders", "-A", is_flag=True, help="Search all folders.")
@click.option("--unread", "-u", is_flag=True, help="Show only unread messages.")
@click.option("--subject", "-s", "subject_filter", default=None, help="Filter by subject.")
@click.option("--sender", "sender_filter", default=None, help="Filter by sender.")
@click.option("--body", "-b", "body_query", default=None, help="Search message body (slower).")
@click.option("--after", default=None, type=click.DateTime(formats=["%Y-%m-%d"]), help="After date (YYYY-MM-DD).")
@click.option("--before", default=None, type=click.DateTime(formats=["%Y-%m-%d"]), help="Before date (YYYY-MM-DD).")
@click.option("--limit", "-n", default=20, help="Max results.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def search_cmd(acct, folder, all_folders, unread, subject_filter, sender_filter, body_query, after, before, limit, as_json):
    """Search messages by metadata or body content."""
    targets = _resolve_targets(acct, folder, all_folders)
    all_results = []

    for alias, config, mailbox in targets:
        try:
            if body_query:
                msgs = applescript.search_body(
                    config["name"], mailbox, body_query, limit=limit,
                    after=after, before=before,
                    subject_filter=subject_filter, sender_filter=sender_filter,
                    unread_only=unread,
                )
            else:
                msgs = applescript.list_messages(
                    config["name"], mailbox, limit=limit,
                    after=after, before=before,
                    subject_filter=subject_filter, sender_filter=sender_filter,
                    unread_only=unread,
                )
            all_results.extend(msgs)
        except RuntimeError as e:
            logger.warning("Error searching %s/%s: %s", alias, mailbox, e)
            continue

    all_results = _sort_by_date(all_results)

    if as_json:
        click.echo(json.dumps(all_results, indent=2))
        return

    if not all_results:
        click.echo("No messages found.")
        return

    show_account = acct is None
    for m in all_results:
        click.echo(_format_msg(m, show_account, show_folder=all_folders))
        if m.get("snippet"):
            click.echo(click.style(f"  {_truncate(m['snippet'], 120)}", fg=DIM))


# --- read ---


@cli.command("read")
@click.argument("identifier")
@click.option("--account", "-a", "acct", default=None, help="Account alias.")
@click.option("--folder", "-f", default=None, help="Mailbox folder.")
@click.option("--format", "fmt", type=click.Choice(["plain", "html", "links"]), default="plain")
@click.option("--max-length", default=None, type=int, help="Truncate body to N chars.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def read_cmd(identifier, acct, folder, fmt, max_length, as_json):
    """Read a message by index (1-based) or message ID.

    Use a number to read by position (e.g. `mail read 1` for the first
    message in a folder). Use a message ID string for exact lookup.
    """
    targets = _resolve_targets(acct, folder, False)
    result = None

    # If identifier looks like an integer, treat as 1-based index
    try:
        idx = int(identifier)
        alias, config, mailbox = targets[0]
        msgs = applescript.list_messages(config["name"], mailbox, limit=idx)
        if idx < 1 or idx > len(msgs):
            click.echo(f"Index {idx} out of range (have {len(msgs)} messages).")
            return
        message_id = msgs[idx - 1]["message_id"]
        result = applescript.read_message(config["name"], mailbox, message_id, fmt=fmt)
    except ValueError:
        # Not an integer, treat as message ID
        message_id = identifier
        for alias, config, mailbox in targets:
            result = applescript.read_message(config["name"], mailbox, message_id, fmt=fmt)
            if result:
                break

    if not result:
        click.echo("Message not found.")
        return

    if max_length and result.get("body"):
        result["body"] = result["body"][:max_length]

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    click.echo(f'{click.style("From:", bold=True)} {result["sender"]}')
    click.echo(f'{click.style("To:", bold=True)} {", ".join(result["to"])}')
    if result["cc"]:
        click.echo(f'{click.style("Cc:", bold=True)} {", ".join(result["cc"])}')
    click.echo(f'{click.style("Date:", bold=True)} {result["date"]}')
    click.echo(f'{click.style("Subject:", bold=True)} {result["subject"]}')
    click.echo()
    click.echo(result.get("body", ""))

    if result.get("links"):
        click.echo(f'\n{click.style("Links:", bold=True)}')
        for i, link in enumerate(result["links"], 1):
            num = click.style(f"  [{i}]", fg=DIM)
            click.echo(f"{num} {link}")


# --- open ---


@cli.command("open")
@click.argument("identifier")
@click.option("--account", "-a", "acct", default=None, help="Account alias.")
@click.option("--folder", "-f", default=None, help="Mailbox folder.")
def open_cmd(identifier, acct, folder):
    """Open a message in Apple Mail by index or message ID."""
    targets = _resolve_targets(acct, folder, False)

    try:
        idx = int(identifier)
        alias, config, mailbox = targets[0]
        msgs = applescript.list_messages(config["name"], mailbox, limit=idx)
        if idx < 1 or idx > len(msgs):
            click.echo(f"Index {idx} out of range (have {len(msgs)} messages).")
            return
        message_id = msgs[idx - 1]["message_id"]
        result = applescript.open_message(config["name"], mailbox, message_id)
    except ValueError:
        message_id = identifier
        result = None
        for alias, config, mailbox in targets:
            try:
                result = applescript.open_message(config["name"], mailbox, message_id)
                if result and result != "message not found":
                    break
            except RuntimeError:
                continue

    if not result or result == "message not found":
        click.echo("Message not found.")
        return
    click.echo(result)


# --- open-link ---


@cli.command("open-link")
@click.argument("identifier")
@click.argument("link_number", type=int)
@click.option("--account", "-a", "acct", default=None, help="Account alias.")
@click.option("--folder", "-f", default=None, help="Mailbox folder.")
def open_link_cmd(identifier, link_number, acct, folder):
    """Open a numbered link from an email in the browser.

    First use `mail read <id> --format links` to see numbered links,
    then `mail open-link <id> <number>` to open one.
    """
    import subprocess

    targets = _resolve_targets(acct, folder, False)
    result = None

    try:
        idx = int(identifier)
        alias, config, mailbox = targets[0]
        msgs = applescript.list_messages(config["name"], mailbox, limit=idx)
        if idx < 1 or idx > len(msgs):
            click.echo(f"Index {idx} out of range.")
            return
        msg_id = msgs[idx - 1]["message_id"]
        result = applescript.read_message(config["name"], mailbox, msg_id, fmt="links")
    except ValueError:
        for alias, config, mailbox in targets:
            result = applescript.read_message(config["name"], mailbox, identifier, fmt="links")
            if result:
                break

    if not result:
        click.echo("Message not found.")
        return

    links = result.get("links", [])
    if link_number < 1 or link_number > len(links):
        click.echo(f"Link {link_number} out of range (have {len(links)} links).")
        return

    url = links[link_number - 1]
    click.echo(f"Opening: {url}")
    subprocess.run(["open", url])


# --- send ---


@cli.command("send")
@click.option("--account", "-a", "acct", required=True, help="Account alias.")
@click.option("--to", "to_addrs", required=True, multiple=True, help="Recipient(s).")
@click.option("--cc", "cc_addrs", multiple=True, help="CC recipient(s).")
@click.option("--bcc", "bcc_addrs", multiple=True, help="BCC recipient(s).")
@click.option("--subject", "-s", required=True)
@click.option("--body", "-b", required=True)
@click.option("--confirm", is_flag=True, help="Actually send (required).")
def send_cmd(acct, to_addrs, cc_addrs, bcc_addrs, subject, body, confirm):
    """Send an email. Requires --confirm to actually send."""
    config = accounts.resolve_account(acct)
    if not confirm:
        click.echo(f'{click.style("From:", bold=True)} {config["email"]}')
        click.echo(f'{click.style("To:", bold=True)} {", ".join(to_addrs)}')
        if cc_addrs:
            click.echo(f'{click.style("Cc:", bold=True)} {", ".join(cc_addrs)}')
        click.echo(f'{click.style("Subject:", bold=True)} {subject}')
        click.echo()
        click.echo(body)
        click.echo(f'\nPass {click.style("--confirm", bold=True)} to actually send.')
        return
    result = applescript.send_email(
        config["name"], config["email"],
        list(to_addrs), subject, body,
        cc=list(cc_addrs) or None, bcc=list(bcc_addrs) or None,
    )
    click.echo(result)


# --- reply ---


@cli.command("reply")
@click.argument("message_id")
@click.option("--account", "-a", "acct", default=None, help="Account alias.")
@click.option("--folder", "-f", default=None, help="Mailbox folder.")
@click.option("--body", "-b", required=True)
@click.option("--all", "reply_all", is_flag=True, help="Reply all.")
@click.option("--confirm", is_flag=True, help="Actually send (required).")
def reply_cmd(message_id, acct, folder, body, reply_all, confirm):
    """Reply to a message. Requires --confirm to actually send."""
    targets = [(acct, accounts.resolve_account(acct))] if acct else accounts.all_accounts()

    config = None
    mailbox = None
    for alias, cfg in targets:
        mailbox = accounts.resolve_folder(alias, folder)
        msg = applescript.read_message(cfg["name"], mailbox, message_id)
        if msg:
            config = cfg
            break

    if not config:
        click.echo("Message not found.")
        return

    if not confirm:
        click.echo(f'{click.style("Replying to:", bold=True)} {msg["subject"]}')
        click.echo(f'{click.style("From:", bold=True)} {msg["sender"]}')
        click.echo(f'{click.style("Body:", bold=True)} {body}')
        click.echo(f'\nPass {click.style("--confirm", bold=True)} to actually send.')
        return

    result = applescript.reply_to_message(config["name"], mailbox, message_id, body, reply_all)
    click.echo(result)


# --- delete ---


@cli.command("delete")
@click.argument("identifier", required=False, default=None)
@click.option("--account", "-a", "acct", required=True, help="Account alias.")
@click.option("--folder", "-f", default=None, help="Mailbox folder.")
@click.option("--ids", default=None, help="Comma-separated message IDs for bulk delete.")
@click.option("--stdin", "from_stdin", is_flag=True, help="Read message IDs from stdin (JSON or one per line).")
@click.option("--confirm", is_flag=True, help="Actually delete (required).")
def delete_cmd(identifier, acct, folder, ids, from_stdin, confirm):
    """Delete messages by index, message ID, --ids, or --stdin. Requires --confirm."""
    config = accounts.resolve_account(acct)
    mailbox = accounts.resolve_folder(acct, folder)

    # Collect message IDs for bulk operation
    bulk_ids = []
    if from_stdin:
        bulk_ids = _read_ids_from_stdin()
    elif ids:
        bulk_ids = [i.strip() for i in ids.split(",") if i.strip()]

    if bulk_ids:
        if not confirm:
            click.echo(f'{click.style("Bulk delete:", bold=True)} {len(bulk_ids)} message(s) from {acct}/{mailbox}')
            click.echo(f'\nPass {click.style("--confirm", bold=True)} to actually delete.')
            return
        count = applescript.bulk_delete(config["name"], mailbox, bulk_ids)
        click.echo(f"Deleted {count}/{len(bulk_ids)} messages.")
        return

    if not identifier:
        click.echo("Provide a message identifier, --ids, or --stdin.")
        return

    message_id = _resolve_msg_id(identifier, config["name"], mailbox)
    if not message_id:
        click.echo("Message not found.")
        return

    msg = applescript.read_message(config["name"], mailbox, message_id)
    if not msg:
        click.echo("Message not found.")
        return

    if not confirm:
        click.echo(f'{click.style("Delete:", bold=True)} {msg["subject"]}')
        click.echo(f'{click.style("From:", bold=True)} {msg["sender"]}')
        click.echo(f'{click.style("Date:", bold=True)} {msg["date"]}')
        click.echo(f'\nPass {click.style("--confirm", bold=True)} to actually delete.')
        return

    result = applescript.delete_message(config["name"], mailbox, message_id)
    click.echo(result)


# --- move ---


@cli.command("move")
@click.argument("identifier", required=False, default=None)
@click.option("--account", "-a", "acct", required=True, help="Account alias.")
@click.option("--from", "-f", "from_folder", default=None, help="Source folder (default: inbox).")
@click.option("--to", "-t", "to_folder", required=True, help="Destination folder.")
@click.option("--ids", default=None, help="Comma-separated message IDs for bulk move.")
@click.option("--stdin", "from_stdin", is_flag=True, help="Read message IDs from stdin (JSON or one per line).")
@click.option("--confirm", is_flag=True, help="Actually move (required).")
def move_cmd(identifier, acct, from_folder, to_folder, ids, from_stdin, confirm):
    """Move messages between folders. Requires --confirm."""
    config = accounts.resolve_account(acct)
    src = accounts.resolve_folder(acct, from_folder)

    # Collect message IDs for bulk operation
    bulk_ids = []
    if from_stdin:
        bulk_ids = _read_ids_from_stdin()
    elif ids:
        bulk_ids = [i.strip() for i in ids.split(",") if i.strip()]

    if bulk_ids:
        if not confirm:
            click.echo(f'{click.style("Bulk move:", bold=True)} {len(bulk_ids)} message(s) from {src} to {to_folder}')
            click.echo(f'\nPass {click.style("--confirm", bold=True)} to actually move.')
            return
        count = applescript.bulk_move(config["name"], src, to_folder, bulk_ids)
        click.echo(f"Moved {count}/{len(bulk_ids)} messages to {to_folder}.")
        return

    if not identifier:
        click.echo("Provide a message identifier, --ids, or --stdin.")
        return

    message_id = _resolve_msg_id(identifier, config["name"], src)
    if not message_id:
        click.echo("Message not found.")
        return

    msg = applescript.read_message(config["name"], src, message_id)
    if not msg:
        click.echo("Message not found.")
        return

    if not confirm:
        click.echo(f'{click.style("Move:", bold=True)} {msg["subject"]}')
        click.echo(f'{click.style("From folder:", bold=True)} {src}')
        click.echo(f'{click.style("To folder:", bold=True)} {to_folder}')
        click.echo(f'\nPass {click.style("--confirm", bold=True)} to actually move.')
        return

    result = applescript.move_message(config["name"], src, to_folder, message_id)
    click.echo(result)
