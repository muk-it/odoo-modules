from __future__ import annotations

import json
import time
from urllib.parse import unquote

from odoo.tools.json import scriptsafe as json_scriptsafe

from odoo.addons.muk_website_cookies_consent.tools.constants import (
    CONSENT_STATE_VERSION,
    ESSENTIAL_CODE,
)


def parse_state(raw: str | None) -> dict | None:
    """Return the decoded consent payload, or None when there is no usable one.

    Anything malformed, truncated or of an unknown payload version is treated
    as absent rather than as a refusal, so a broken cookie makes the banner
    reappear instead of locking the visitor into a decision they never made.
    The value is percent-encoded by the browser; unquoting one that is not
    encoded is harmless.
    """
    if not raw:
        return None
    try:
        state = json_scriptsafe.loads(unquote(raw))
    except (ValueError, TypeError):
        return None
    if not isinstance(state, dict) or state.get('v') != CONSENT_STATE_VERSION:
        return None
    if not isinstance(state.get('cats'), list) or not isinstance(state.get('ts'), int):
        return None
    return state


def serialise_state(state: dict) -> str:
    """Return the payload as compact JSON.

    The browser percent-encodes it before storing it; this is the plain form,
    which :func:`parse_state` also accepts.
    """
    return json.dumps(state, separators=(',', ':'), sort_keys=True)


def build_state(
    categories: list[str],
    services: list[str],
    policy_version: int,
    registry_hash: str,
    lang_code: str,
    consent_uid: str = '',
    timestamp: int | None = None,
    first_timestamp: int | None = None,
    answered: bool = True,
) -> dict:
    """Return a fresh consent payload for the given decision.

    ``essential`` is always present: it is not consented to, it is simply
    always true, and writing it keeps the payload self-describing.

    :param timestamp: the moment of this decision, defaulting to now
    :param first_timestamp: the moment of the visitor's first ever decision
    :param answered: False when only an embed was allowed, which answers
        nothing the banner asked and so must not silence it
    """
    now = int(timestamp if timestamp is not None else time.time())
    granted = [ESSENTIAL_CODE] + [c for c in categories if c != ESSENTIAL_CODE]
    return {
        'v': CONSENT_STATE_VERSION,
        'uid': consent_uid,
        'ans': 1 if answered else 0,
        'cats': granted,
        'svcs': sorted(services),
        'pv': policy_version,
        'rh': registry_hash,
        'ts': int(first_timestamp if first_timestamp is not None else now),
        'rts': now,
        'lang': lang_code or '',
    }


def is_current(
    state: dict | None,
    policy_version: int,
    registry_hash: str,
    lifetime_days: int,
    now: int | None = None,
) -> bool:
    """Return whether a stored decision may still be relied on.

    A decision stops counting when the policy version or the registry hash
    moves — a new purpose or vendor must never ride on an older consent — or
    when it is older than the configured lifetime.
    """
    if not state:
        return False
    if state.get('pv') != policy_version or state.get('rh') != registry_hash:
        return False
    decided = state.get('rts') or state.get('ts') or 0
    age = int(now if now is not None else time.time()) - int(decided)
    return 0 <= age <= lifetime_days * 86400


def granted_categories(state: dict | None) -> set[str]:
    """Return the category codes a payload grants, always including essential."""
    if not state:
        return {ESSENTIAL_CODE}
    codes = {str(code) for code in state.get('cats') or []}
    codes.add(ESSENTIAL_CODE)
    return codes


def granted_services(state: dict | None) -> set[str]:
    """Return the service technical names a payload grants."""
    if not state:
        return set()
    return {str(name) for name in state.get('svcs') or []}
