"""Read a credential without putting it in arguments, history, or a config file."""

import getpass
import sys
import warnings


def prompt_api_key() -> str:
    if not sys.stdin.isatty():
        raise ValueError("enter the API key in an interactive terminal, or set CODEMAP_REMOTE_KEY")
    try:
        with warnings.catch_warnings():
            # getpass otherwise falls back to an echoed prompt on some terminals.
            warnings.simplefilter("error", getpass.GetPassWarning)
            key = getpass.getpass("API key (hidden; not saved): ").strip()
    except (getpass.GetPassWarning, EOFError):
        raise ValueError("cannot read a hidden API key in this terminal") from None
    if not key or len(key) > 4096 or any(not 33 <= ord(c) <= 126 for c in key):
        raise ValueError("API key is empty or contains invalid characters")
    return key
