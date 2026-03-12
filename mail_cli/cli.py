"""CLI entry point for mail-cli."""

import json

import click

from . import accounts, applescript

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


@cli.command("folders")
@click.option("--account", "-a", "acct", default=None, help="Account alias.")
def folders_cmd(acct: str | None):
    """List mailbox folders."""
    targets = [(acct, accounts.resolve_account(acct))] if acct else accounts.all_accounts()
    for alias, config in targets:
        folders = applescript.list_folders(config["name"])
        label = click.style(alias, bold=True)
        click.echo(f"{label}: {', '.join(folders)}")


# --- list ---


@cli.command("list")
@click.option("--account", "-a", "acct", default=None, help="Account alias.")
@click.option("--folder", "-f", default=None, help="Mailbox folder (default: inbox).")
@click.option("--all-folders", "-A", is_flag=True, help="Search all folders.")
@click.option("--limit", "-n", default=20, help="Number of messages.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def list_cmd(acct: str | None, folder: str | None, all_folders: bool, limit: int, as_json: bool):
    """List recent messages."""
    targets = _resolve_targets(acct, folder, all_folders)
    all_msgs = []
    for alias, config, mailbox in targets:
        try:
            msgs = applescript.list_messages(config["name"], mailbox, limit=limit)
            all_msgs.extend(msgs)
        except RuntimeError:
            continue

    if as_json:
        click.echo(json.dumps(all_msgs, indent=2))
        return

    if not all_msgs:
        click.echo("No messages found.")
        return

    show_account = acct is None
    for m in all_msgs:
        click.echo(_format_msg(m, show_account, show_folder=all_folders))


# --- search ---


@cli.command("search")
@click.option("--account", "-a", "acct", default=None, help="Account alias.")
@click.option("--folder", "-f", default=None, help="Mailbox folder (default: inbox).")
@click.option("--all-folders", "-A", is_flag=True, help="Search all folders.")
@click.option("--subject", "-s", "subject_filter", default=None, help="Filter by subject.")
@click.option("--sender", "sender_filter", default=None, help="Filter by sender.")
@click.option("--body", "-b", "body_query", default=None, help="Search message body (slower).")
@click.option("--after", default=None, type=click.DateTime(formats=["%Y-%m-%d"]), help="After date (YYYY-MM-DD).")
@click.option("--before", default=None, type=click.DateTime(formats=["%Y-%m-%d"]), help="Before date (YYYY-MM-DD).")
@click.option("--limit", "-n", default=20, help="Max results.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def search_cmd(acct, folder, all_folders, subject_filter, sender_filter, body_query, after, before, limit, as_json):
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
                )
            else:
                msgs = applescript.list_messages(
                    config["name"], mailbox, limit=limit,
                    after=after, before=before,
                    subject_filter=subject_filter, sender_filter=sender_filter,
                )
            all_results.extend(msgs)
        except RuntimeError:
            continue

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
        for link in result["links"]:
            click.echo(f"  {link}")


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
