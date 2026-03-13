"""Account configuration and mailbox name normalization.

Reads account config from ~/.config/email-cli/accounts.json.
Run `email accounts init` to create the config interactively.
"""

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "email-cli"
CONFIG_FILE = CONFIG_DIR / "accounts.json"

# Cache
_accounts: dict | None = None


def _load() -> dict:
    global _accounts
    if _accounts is not None:
        return _accounts
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"No config found at {CONFIG_FILE}. Run `email accounts init` to set up."
        )
    _accounts = json.loads(CONFIG_FILE.read_text())
    return _accounts


def save(accounts: dict) -> None:
    global _accounts
    # Check for duplicate account names
    names = {}
    for alias, config in accounts.items():
        name_lower = config["name"].lower()
        if name_lower in names:
            raise ValueError(
                f"Duplicate account name {config['name']!r} "
                f"in aliases {names[name_lower]!r} and {alias!r}"
            )
        names[name_lower] = alias
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(accounts, indent=2) + "\n")
    _accounts = accounts


def resolve_account(alias: str) -> dict:
    accounts = _load()
    key = alias.lower()
    if key in accounts:
        return accounts[key]
    # Try matching by full name
    for k, v in accounts.items():
        if v["name"].lower() == key:
            return v
    raise ValueError(f"Unknown account: {alias!r}. Available: {', '.join(accounts)}")


def resolve_folder(account_alias: str, folder: str | None) -> str:
    acct = resolve_account(account_alias)
    if folder is None or folder.lower() == "inbox":
        return acct["inbox"]
    return folder


def all_accounts() -> list[tuple[str, dict]]:
    return list(_load().items())
