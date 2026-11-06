from __future__ import annotations

import re
from pathlib import Path

import requests

IMAGE_TAGS_URL = 'https://hub.docker.com/v2/repositories/library/odoo/tags'
IMAGE_TAG = re.compile(r'(\d+\.0)-(\d{8})')
PACKAGE_STATUS = Path('/var/lib/dpkg/status')
PACKAGE_VERSION = re.compile(
    r'^Package: odoo\n(?:.+\n)*?Status: install ok installed\n'
    r'(?:.+\n)*?Version: \S+\.(\d{8})',
    re.MULTILINE,
)


def fetch_image_builds() -> dict[str, str]:
    """Return the newest build date of each series with an official image."""
    response = requests.get(
        IMAGE_TAGS_URL,
        params={'page_size': 100, 'ordering': 'last_updated'},
        timeout=10,
    )
    response.raise_for_status()
    builds = {}
    for tag in response.json()['results']:
        if match := IMAGE_TAG.fullmatch(tag['name']):
            series, date = match.groups()
            builds[series] = max(date, builds.get(series, ''))
    return builds


def installed_build() -> str | None:
    """Return the build date of the installed Odoo package, if there is one."""
    if not PACKAGE_STATUS.is_file():
        return None
    match = PACKAGE_VERSION.search(PACKAGE_STATUS.read_text(encoding='utf-8'))
    return match and match[1]
