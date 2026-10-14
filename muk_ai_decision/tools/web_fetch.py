from __future__ import annotations

import logging

import urllib3

from odoo.exceptions import UserError

from odoo.addons.muk_ai.tools.url_fetch import fetch_url, render_content

_logger = logging.getLogger(__name__)


def web_fetch(url: str, headers: dict | None = None) -> str:
    """Fetch ``url`` as readable text, empty when there is none or the fetch fails.

    :param headers: extra request headers, such as the key of an API
    """
    if not url:
        return ''
    try:
        return render_content(fetch_url(url, headers=headers))[1]
    except (UserError, urllib3.exceptions.HTTPError) as error:
        _logger.info('Decision input %s could not be fetched: %s', url, error)
        return ''
