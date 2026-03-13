"""AppleScript generation, execution, and output parsing."""

import subprocess
from datetime import datetime
from email import policy
from email.parser import BytesParser
import html.parser
import re


FIELD_DELIM = "~FLD~"
ROW_DELIM = "~ROW~"
TIMEOUT = 60


def _run(script: str, timeout: int = TIMEOUT) -> str:
    r = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=timeout,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r.stdout.strip()


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _as_date(dt: datetime) -> str:
    return dt.strftime('date "%A, %B %d, %Y at %H:%M:%S"')


def check_for_new_mail() -> str:
    return _run('tell application "Mail" to check for new mail')


def _mailbox_ref(folder: str, account_name: str) -> str:
    """Convert a folder path like 'Housing/Sonneggstrasse 4' to an AppleScript
    mailbox reference like: mailbox "Sonneggstrasse 4" of mailbox "Housing" of account "iCloud"
    """
    parts = folder.split("/")
    ref = f'account "{_esc(account_name)}"'
    for part in parts:
        ref = f'mailbox "{_esc(part)}" of {ref}'
    return ref


def list_folders(account_name: str) -> list[str]:
    script = f'''tell application "Mail"
    set acct to account "{_esc(account_name)}"
    set allMb to every mailbox of acct
    set output to ""
    repeat with mb in allMb
        set n to name of mb
        set thePath to n
        try
            set cont to container of mb
            set contClass to class of cont as string
            if contClass is "container" then
                set thePath to (name of cont) & "/" & n
            end if
        end try
        if output is not "" then set output to output & ","
        set output to output & thePath
    end repeat
    return output
end tell'''
    raw = _run(script)
    if not raw:
        return []
    return [f.strip() for f in raw.split(",")]


def list_messages(
    account_name: str,
    folder: str,
    limit: int = 20,
    after: datetime | None = None,
    before: datetime | None = None,
    subject_filter: str | None = None,
    sender_filter: str | None = None,
    unread_only: bool = False,
) -> list[dict]:
    conditions = []
    if subject_filter:
        conditions.append(f'subject contains "{_esc(subject_filter)}"')
    if sender_filter:
        conditions.append(f'sender contains "{_esc(sender_filter)}"')
    if after:
        conditions.append(f"date received > {_as_date(after)}")
    if before:
        conditions.append(f"date received < {_as_date(before)}")
    if unread_only:
        conditions.append("read status is false")

    whose = ""
    if conditions:
        whose = " whose " + " and ".join(conditions)

    fd, rd = FIELD_DELIM, ROW_DELIM
    mb_ref = _mailbox_ref(folder, account_name)
    script = f'''
tell application "Mail"
    set fieldSep to "{fd}"
    set rowSep to "{rd}"
    set msgs to (every message of {mb_ref}{whose})
    set maxN to {limit}
    set c to count of msgs
    if c < maxN then set maxN to c
    set output to ""
    repeat with i from 1 to maxN
        set m to item i of msgs
        set mid to message id of m
        set subj to subject of m
        set sndr to sender of m
        set dateStr to date received of m as string
        set readStr to read status of m as string
        set output to output & mid & fieldSep & subj & fieldSep & sndr & fieldSep & dateStr & fieldSep & readStr
        if i < maxN then set output to output & rowSep
    end repeat
    return output
end tell'''
    raw = _run(script)
    if not raw:
        return []
    results = []
    for row in raw.split(rd):
        parts = row.split(fd)
        if len(parts) < 5:
            continue
        results.append({
            "message_id": parts[0],
            "subject": parts[1],
            "sender": parts[2],
            "date": parts[3],
            "read": parts[4] == "true",
            "account": account_name,
            "folder": folder,
        })
    return results


def read_message(account_name: str, folder: str, message_id: str, fmt: str = "plain") -> dict:
    fd = FIELD_DELIM
    if fmt == "plain":
        content_expr = "content of m"
    else:
        content_expr = "source of m"

    mb_ref = _mailbox_ref(folder, account_name)
    script = f'''
tell application "Mail"
    set fd to "{fd}"
    set mb to {mb_ref}
    set matches to (every message of mb whose message id is "{_esc(message_id)}")
    if (count of matches) is 0 then return ""
    set m to item 1 of matches
    set subj to subject of m
    set sndr to sender of m
    set dr to date received of m as string
    set toList to ""
    repeat with r in to recipients of m
        set toList to toList & address of r & ", "
    end repeat
    set ccList to ""
    repeat with r in cc recipients of m
        set ccList to ccList & address of r & ", "
    end repeat
    set body to {content_expr}
    return subj & fd & sndr & fd & dr & fd & toList & fd & ccList & fd & body
end tell'''
    raw = _run(script)
    if not raw:
        return {}
    parts = raw.split(fd, 5)
    if len(parts) < 6:
        return {}

    body = parts[5]
    links = []

    if fmt == "links":
        body, links = _extract_links(parts[5])
    elif fmt == "html":
        body = _extract_html(parts[5])

    return {
        "message_id": message_id,
        "subject": parts[0],
        "sender": parts[1],
        "date": parts[2],
        "to": [a.strip() for a in parts[3].split(",") if a.strip()],
        "cc": [a.strip() for a in parts[4].split(",") if a.strip()],
        "body": body,
        "links": links,
    }


def search_body(
    account_name: str,
    folder: str,
    query: str,
    limit: int = 20,
    after: datetime | None = None,
    before: datetime | None = None,
    subject_filter: str | None = None,
    sender_filter: str | None = None,
    unread_only: bool = False,
    batch_size: int = 50,
) -> list[dict]:
    # First get candidate messages using metadata filters
    candidates = list_messages(
        account_name, folder, limit=500,
        after=after, before=before,
        subject_filter=subject_filter, sender_filter=sender_filter,
        unread_only=unread_only,
    )
    if not candidates:
        return []

    query_lower = query.lower()
    results = []

    # Fetch content in batches
    for i in range(0, len(candidates), batch_size):
        if len(results) >= limit:
            break
        batch = candidates[i:i + batch_size]
        contents = _batch_fetch_content(account_name, folder, [c["message_id"] for c in batch])
        for msg, content in zip(batch, contents):
            if query_lower in content.lower():
                msg["snippet"] = _snippet(content, query, context_chars=100)
                results.append(msg)
                if len(results) >= limit:
                    break

    return results


def send_email(
    account_name: str,
    email_address: str,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
) -> str:
    recipients = ""
    for addr in to:
        recipients += f'        make new to recipient at end of to recipients with properties {{address:"{_esc(addr)}"}}\n'
    for addr in (cc or []):
        recipients += f'        make new cc recipient at end of cc recipients with properties {{address:"{_esc(addr)}"}}\n'
    for addr in (bcc or []):
        recipients += f'        make new bcc recipient at end of bcc recipients with properties {{address:"{_esc(addr)}"}}\n'

    script = f'''
tell application "Mail"
    set newMsg to make new outgoing message with properties {{subject:"{_esc(subject)}", content:"{_esc(body)}", sender:"{_esc(email_address)}", visible:false}}
    tell newMsg
{recipients}    end tell
    send newMsg
end tell
return "sent"'''
    return _run(script)


def reply_to_message(
    account_name: str,
    folder: str,
    message_id: str,
    body: str,
    reply_all: bool = False,
) -> str:
    reply_clause = "opening window" if reply_all else ""
    mb_ref = _mailbox_ref(folder, account_name)
    script = f'''
tell application "Mail"
    set mb to {mb_ref}
    set matches to (every message of mb whose message id is "{_esc(message_id)}")
    if (count of matches) is 0 then return "message not found"
    set m to item 1 of matches
    set replyMsg to reply m {reply_clause} with properties {{content:"{_esc(body)}"}}
    send replyMsg
end tell
return "sent"'''
    return _run(script)


def open_message(account_name: str, folder: str, message_id: str) -> str:
    mb_ref = _mailbox_ref(folder, account_name)
    script = f'''
tell application "Mail"
    set mb to {mb_ref}
    set matches to (every message of mb whose message id is "{_esc(message_id)}")
    if (count of matches) is 0 then return "message not found"
    set m to item 1 of matches
    set msgId to id of m
    activate
    set theURL to "message:%3C" & message id of m & "%3E"
    open location theURL
    return "opened"
end tell'''
    return _run(script)


def delete_message(account_name: str, folder: str, message_id: str) -> str:
    mb_ref = _mailbox_ref(folder, account_name)
    script = f'''
tell application "Mail"
    set mb to {mb_ref}
    set matches to (every message of mb whose message id is "{_esc(message_id)}")
    if (count of matches) is 0 then return "message not found"
    set targetMsg to item 1 of matches
    delete targetMsg
    return "deleted"
end tell'''
    return _run(script)


def create_folder(account_name: str, folder_name: str) -> str:
    mb_ref = _mailbox_ref(folder_name, account_name)
    script = f'''
tell application "Mail"
    try
        set existing to {mb_ref}
        return "already exists"
    end try
    make new mailbox with properties {{name:"{_esc(folder_name)}"}} at account "{_esc(account_name)}"
    return "created"
end tell'''
    return _run(script)


def delete_folder(account_name: str, folder_name: str) -> str:
    mb_ref = _mailbox_ref(folder_name, account_name)
    script = f'''
tell application "Mail"
    set mb to {mb_ref}
    delete mb
    return "deleted"
end tell'''
    return _run(script)


def bulk_delete(account_name: str, folder: str, message_ids: list[str]) -> int:
    if not message_ids:
        return 0
    delete_blocks = ""
    for mid in message_ids:
        delete_blocks += f'''
        try
            set matches to (every message of mb whose message id is "{_esc(mid)}")
            if (count of matches) > 0 then
                delete item 1 of matches
                set deleted to deleted + 1
            end if
        end try
'''
    mb_ref = _mailbox_ref(folder, account_name)
    script = f'''
tell application "Mail"
    set mb to {mb_ref}
    set deleted to 0
{delete_blocks}
    return deleted as string
end tell'''
    result = _run(script, timeout=120)
    try:
        return int(result)
    except ValueError:
        return 0


def bulk_move(account_name: str, from_folder: str, to_folder: str, message_ids: list[str]) -> int:
    if not message_ids:
        return 0
    move_blocks = ""
    for mid in message_ids:
        move_blocks += f'''
        try
            set matches to (every message of srcMb whose message id is "{_esc(mid)}")
            if (count of matches) > 0 then
                move item 1 of matches to dstMb
                set moved to moved + 1
            end if
        end try
'''
    src_ref = _mailbox_ref(from_folder, account_name)
    dst_ref = _mailbox_ref(to_folder, account_name)
    script = f'''
tell application "Mail"
    set srcMb to {src_ref}
    set dstMb to {dst_ref}
    set moved to 0
{move_blocks}
    return moved as string
end tell'''
    result = _run(script, timeout=120)
    try:
        return int(result)
    except ValueError:
        return 0


def move_message(account_name: str, from_folder: str, to_folder: str, message_id: str) -> str:
    src_ref = _mailbox_ref(from_folder, account_name)
    dst_ref = _mailbox_ref(to_folder, account_name)
    script = f'''
tell application "Mail"
    set srcMb to {src_ref}
    set dstMb to {dst_ref}
    set matches to (every message of srcMb whose message id is "{_esc(message_id)}")
    if (count of matches) is 0 then return "message not found"
    set targetMsg to item 1 of matches
    move targetMsg to dstMb
    return "moved"
end tell'''
    return _run(script)


# --- internal helpers ---


def _batch_fetch_content(account_name: str, folder: str, message_ids: list[str]) -> list[str]:
    if not message_ids:
        return []
    rd = ROW_DELIM
    id_checks = " or ".join(f'message id of m is "{_esc(mid)}"' for mid in message_ids)

    # Simpler approach: fetch by index from a pre-filtered list
    # AppleScript doesn't support OR in whose, so fetch one at a time in a single script
    fetch_blocks = ""
    for mid in message_ids:
        fetch_blocks += f'''
        try
            set matches to (every message of mb whose message id is "{_esc(mid)}")
            if (count of matches) > 0 then
                set m to item 1 of matches
                set c to content of m
                set output to output & c & "{rd}"
            else
                set output to output & "" & "{rd}"
            end if
        on error
            set output to output & "" & "{rd}"
        end try
'''

    mb_ref = _mailbox_ref(folder, account_name)
    script = f'''
tell application "Mail"
    set mb to {mb_ref}
    set output to ""
{fetch_blocks}
    return output
end tell'''

    raw = _run(script, timeout=120)
    parts = raw.split(rd)
    # Remove trailing empty element from final delimiter
    if parts and parts[-1] == "":
        parts = parts[:-1]
    # Pad to match input length
    while len(parts) < len(message_ids):
        parts.append("")
    return parts


def _snippet(text: str, query: str, context_chars: int = 100) -> str:
    idx = text.lower().find(query.lower())
    if idx < 0:
        return text[:200]
    start = max(0, idx - context_chars)
    end = min(len(text), idx + len(query) + context_chars)
    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


def _extract_html(mime_source: str) -> str:
    try:
        msg = BytesParser(policy=policy.default).parsebytes(mime_source.encode("utf-8", errors="replace"))
        html_part = msg.get_body(preferencelist=("html",))
        if html_part:
            return html_part.get_content()
    except Exception:
        pass
    return mime_source


_URL_RE = re.compile(r'https?://[^\s<>"\')\]]+')


class _LinkExtractor(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self.links.append(value)


def _extract_links(mime_source: str) -> tuple[str, list[str]]:
    html_body = _extract_html(mime_source)
    parser = _LinkExtractor()
    try:
        parser.feed(html_body)
    except Exception:
        pass

    links = parser.links
    # Fall back to regex URL extraction for plain-text emails
    if not links:
        links = _URL_RE.findall(html_body)

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for link in links:
        if link not in seen:
            seen.add(link)
            unique.append(link)

    return html_body, unique
