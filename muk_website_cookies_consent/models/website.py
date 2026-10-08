from __future__ import annotations

import functools
import hashlib
import json
import logging
from urllib.parse import quote, urljoin, urlsplit

import requests
from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import MissingError, UserError
from odoo.http import request

from odoo.addons.muk_website_cookies_consent.tools.consent import (
    build_state,
    granted_categories,
    granted_services,
    is_current,
    parse_state,
    serialise_state,
)
from odoo.addons.muk_website_cookies_consent.tools.constants import (
    CONSENT_COOKIE,
    CONSENT_MODE_HOSTS,
    CONSENT_MODE_SIGNALS,
    CONSENT_MODE_WAIT_FOR_UPDATE,
    COOKIE_POLICY_PATH,
    DEFAULT_LIFETIME_DAYS,
    ESSENTIAL_CODE,
    REGISTRY_HASH_LENGTH,
    SCAN_LOCK_NAMESPACE,
    SCAN_PAGE_LIMIT,
    SCAN_TIMEOUT,
    SCAN_USER_AGENT,
    UNCLASSIFIED_CODE,
)
from odoo.addons.muk_website_cookies_consent.tools.scanner import (
    extract_keys,
    normalise_host,
)

_logger = logging.getLogger(__name__)


def memoise_per_request(method):
    """Compute a visitor-dependent answer once per request.

    The gating is asked once per element core post-processes, thousands of
    times on a long shop page, while everything it reads off the visitor (the
    consent cookie, the GPC header, the country, the user) is fixed for the
    length of a request. Keyed on the website and the user, because the
    editor exemption depends on who renders. Without a request there is
    nothing to keep the answer on, so it is computed every time.
    """

    @functools.wraps(method)
    def wrapper(self):
        if not request:
            return method(self)
        memo = getattr(request, '_muk_cookie_consent_memo', None)
        if memo is None:
            memo = request._muk_cookie_consent_memo = {}
        key = (method.__name__, self.id, self.env.uid)
        if key not in memo:
            memo[key] = method(self)
        return memo[key]

    return wrapper


class Website(models.Model):
    """Configure and resolve granular cookie consent for the website."""

    _inherit = 'website'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    cookie_layout = fields.Selection(
        selection=[
            ('bar_bottom', 'Bar at the bottom'),
            ('bar_top', 'Bar at the top'),
            ('box_left', 'Box, bottom left'),
            ('box_right', 'Box, bottom right'),
            ('center', 'Centred dialog'),
        ],
        string='Banner Layout',
        required=True,
        default='bar_bottom',
    )

    cookie_density = fields.Selection(
        selection=[
            ('full', 'Full (heading and explanation)'),
            ('compact', 'Compact (one line)'),
        ],
        string='Banner Density',
        help=(
            'How much of the notice is shown. Compact hides the heading and '
            'tightens the spacing; what the visitor is told does not change, '
            'because the disclosure is not a matter of taste.'
        ),
        required=True,
        default='full',
    )

    cookie_policy_version = fields.Integer(
        string='Policy Version',
        help=(
            'Raising this invalidates every stored decision and asks all '
            'visitors again. Use it when the disclosure itself changes.'
        ),
        required=True,
        default=1,
    )

    cookie_consent_mode = fields.Selection(
        selection=[
            ('basic', 'Basic (hold tags until consent)'),
            ('advanced', 'Advanced (cookieless pings before consent)'),
        ],
        string='Google Consent Mode',
        help=(
            'Basic withholds Google tags entirely until a purpose they serve '
            'is granted, so a refusal keeps them unloaded. Advanced loads them '
            'immediately and lets them send cookieless pings, which recovers '
            'conversion modelling but sends data before any consent.'
        ),
        required=True,
        default='basic',
    )

    cookie_reopen_float = fields.Selection(
        selection=[
            ('none', 'No floating button'),
            ('left', 'Bottom left'),
            ('right', 'Bottom right'),
        ],
        string='Floating Button',
        required=True,
        default='right',
    )

    cookie_scan_date = fields.Datetime(
        string='Last Scan',
        readonly=True,
    )

    cookie_scan_count = fields.Integer(
        string='Pages Scanned',
        readonly=True,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _is_cookie_consent_active(self) -> bool:
        """Return whether this module governs consent on this website.

        Bound to core's own switch: the native bar's server-side gating, its
        policy page and its embed stripping all stay in play, and this module
        replaces only the interface and the granularity.
        """
        return bool(self.cookies_bar)

    def _get_cookie_domain(self) -> list:
        """Return the domain selecting this website's records and the global ones."""
        return [('website_id', 'in', [self.id, False])]

    def _get_cookie_policy_url(self) -> str:
        """Return where the banner points visitors for the full policy."""
        return self.cookie_policy_id.sudo().url or COOKIE_POLICY_PATH

    @api.ormcache('self.id')
    def _get_cookie_category_ids(self) -> tuple:
        """Return the ids of the purposes offered on this website, essential first.

        Memoised because core asks the gating once per element it
        post-processes, where a plain search costs thousands of queries per
        page. Dropped on write through the registry mixin.
        """
        return tuple(
            self.env['muk_website_cookies_consent.category']
            .sudo()
            .search(self._get_cookie_domain())
            .sorted(lambda c: (not c.essential, c.sequence, c.id))
            .ids
        )

    def _get_cookie_categories(self) -> models.Model:
        """Return the purposes offered on this website, essential first."""
        return (
            self.env['muk_website_cookies_consent.category']
            .sudo()
            .browse(self._get_cookie_category_ids())
        )

    def _get_offered_cookie_categories(self) -> models.Model:
        """Return the purposes worth putting to the visitor.

        An empty purpose is noise; emptiness is judged on this website's records.
        ``unclassified`` is never offered: consent cannot be informed for keys
        with no described purpose, so they stay refused until classified.
        """
        populated = self._get_populated_cookie_category_ids()
        return self._get_cookie_categories().filtered(
            lambda c: c.code != UNCLASSIFIED_CODE and (c.essential or c.id in populated)
        )

    @api.ormcache('self.id')
    def _get_populated_cookie_category_ids(self) -> tuple:
        """Return the ids of purposes this website declares anything under.

        Memoised with the rest of the registry: the gating asks which purposes
        are on offer once per rendered element, so resolving it through the
        one2manys would put a query back on that path.
        """
        declarations = self._get_cookie_declarations()
        services = self._get_cookie_services()
        return tuple(set(declarations.category_id.ids) | set(services.category_id.ids))

    def _get_optional_cookie_categories(self) -> models.Model:
        """Return the purposes the visitor actually decides on.

        Restricted to what the dialog offers, so the server's idea of full
        consent cannot include a purpose the visitor was never shown.
        """
        return self._get_offered_cookie_categories().filtered(lambda c: not c.essential)

    def _get_cookie_declarations_of(self, category: models.Model) -> models.Model:
        """Return this website's declarations filed under one purpose.

        The purpose's own one2many spans every website, so reading it would
        disclose another site's cookies in this site's dialog and policy.
        """
        return self._get_cookie_declarations().filtered(
            lambda c: c.category_id == category
        )

    @api.ormcache('self.id')
    def _get_cookie_service_ids(self) -> tuple:
        """Return the ids of the gated services declared on this website."""
        return tuple(
            self.env['muk_website_cookies_consent.service']
            .sudo()
            .search(self._get_cookie_domain())
            .ids
        )

    def _get_cookie_services(self) -> models.Model:
        """Return the gated services declared on this website."""
        return (
            self.env['muk_website_cookies_consent.service']
            .sudo()
            .browse(self._get_cookie_service_ids())
        )

    @api.ormcache('self.id')
    def _get_cookie_declaration_ids(self) -> tuple:
        """Return the ids of the cookies declared on this website."""
        return tuple(
            self.env['muk_website_cookies_consent.cookie']
            .sudo()
            .search(self._get_cookie_domain())
            .ids
        )

    def _get_cookie_declarations(self) -> models.Model:
        """Return the declared cookies, for the policy table and clearing.

        Filtered through ``exists()``: the memoised ids can outlive a deletion in
        another process, and one stale id would break every page render.
        """
        return (
            self.env['muk_website_cookies_consent.cookie']
            .sudo()
            .browse(self._get_cookie_declaration_ids())
            .exists()
        )

    @api.ormcache('self.id')
    def _get_cookie_registry_hash(self) -> str:
        """Return a fingerprint of everything the banner discloses.

        A new purpose, service, host or declared cookie changes it, which
        invalidates every consent given against the older disclosure. Memoised,
        so the ``exists()`` guards are paid once per change, not per element.
        """
        parts = []
        for category in self._get_cookie_categories().exists():
            parts.append(f'c:{category.code}:{category.essential:d}')
        for service in self._get_cookie_services().exists():
            hosts = ','.join(service._get_domain_list())
            parts.append(
                f's:{service.technical_name}:{service.category_id.code}:{hosts}'
            )
        for cookie in self._get_cookie_declarations():
            parts.append(f'k:{cookie.name}:{cookie.category_id.code}')
        digest = hashlib.sha256('|'.join(parts).encode()).hexdigest()
        return digest[:REGISTRY_HASH_LENGTH]

    @api.model
    def _clear_cookie_registry_cache(self) -> None:
        """Drop everything derived from the registry after it changes.

        The fingerprint is memoised, and it is baked into pages that Odoo
        caches, so both have to go or a stale page keeps quoting the old one.
        """
        self.env.transaction.invalidate_ormcache()
        self.env.transaction.invalidate_ormcache('templates')

    def _is_gpc_requested(self) -> bool:
        """Return whether the request carries a Global Privacy Control signal.

        Only the exact value ``1`` counts; the specification says anything
        else must be ignored.
        """
        if not request:
            return False
        return request.httprequest.headers.get('Sec-GPC') == '1'

    def _get_cookie_geo_rule(self) -> models.Model:
        """Return the region rule that applies to the current request."""
        country_code = None
        if request:
            country_code = request.geoip.country_code
        return self.env['muk_website_cookies_consent.geo.rule']._find_for_country(
            country_code, self
        )

    def _get_cookie_lifetime_days(self) -> int:
        """Return how many days a decision is relied on for this request.

        The rule id is memoised, so a deletion elsewhere can outlive it. This
        runs before every gate, where a query to check would cost one per
        rendered element, so the stale cache is dropped on the miss instead.
        """
        rule = self._get_cookie_geo_rule()
        if not rule:
            return DEFAULT_LIFETIME_DAYS
        try:
            return rule.lifetime_days
        except MissingError:
            self._clear_cookie_registry_cache()
            return DEFAULT_LIFETIME_DAYS

    def _get_cookie_state(self) -> dict | None:
        """Return the visitor's stored decision, or None when there is none."""
        if not request:
            return None
        return parse_state(request.cookies.get(CONSENT_COOKIE))

    def _has_cookie_record(self) -> bool:
        """Return whether a usable consent payload is on record for this visitor."""
        return is_current(
            self._get_cookie_state(),
            self.cookie_policy_version,
            self._get_cookie_registry_hash(),
            self._get_cookie_lifetime_days(),
        )

    def _has_cookie_decision(self) -> bool:
        """Return whether the visitor has answered the question the banner asks.

        Allowing one embed in place writes a record but answers nothing. A
        payload without the ``ans`` flag counts as answered.
        """
        if not self._has_cookie_record():
            return False
        return bool((self._get_cookie_state() or {}).get('ans', 1))

    def _get_known_cookie_codes(self) -> set[str]:
        """Return the purpose codes a visitor is able to grant.

        The offered set rather than every declared one: a purpose the dialog
        never put to the visitor cannot have been consented to, however the
        cookie arrives.
        """
        return set(self._get_offered_cookie_categories().mapped('code'))

    @memoise_per_request
    def _get_granted_cookie_codes(self) -> frozenset[str]:
        """Return the purpose codes in force for the current request.

        Global Privacy Control overrides the stored decision. The result is
        narrowed to declared codes, so a forged cookie cannot mint cache keys.
        """
        if self._is_gpc_requested():
            return frozenset({ESSENTIAL_CODE})
        if not self._has_cookie_decision():
            return frozenset({ESSENTIAL_CODE})
        granted = granted_categories(self._get_cookie_state())
        return frozenset(granted & self._get_known_cookie_codes()) | {ESSENTIAL_CODE}

    @memoise_per_request
    def _get_granted_cookie_services(self) -> frozenset[str]:
        """Return the service names granted for the current request.

        Keyed on the record rather than on an answered decision: allowing an
        embed in place grants that one service without answering anything.
        """
        if not self._has_cookie_record() or self._is_gpc_requested():
            return frozenset()
        known = set(self._get_cookie_services().mapped('technical_name'))
        return frozenset(granted_services(self._get_cookie_state()) & known)

    def _get_cookie_consent_key(self) -> str:
        """Return the granted purposes and services as one cache key part."""
        categories = ','.join(sorted(self._get_granted_cookie_codes()))
        services = ','.join(sorted(self._get_granted_cookie_services()))
        return f'{categories}|{services}'

    def _is_cookie_category_granted(self, code: str) -> bool:
        """Return whether a purpose is granted for the current request."""
        if code == ESSENTIAL_CODE:
            return True
        return code in self._get_granted_cookie_codes()

    def _is_cookie_service_granted(self, service: models.Model) -> bool:
        """Return whether a service may run for the current request.

        A service needs its purpose granted. Services asked for in place get an
        additional per-service grant, so accepting one video embed never
        enables the rest of the purpose or flips its Consent Mode signals.
        """
        if service.technical_name in self._get_granted_cookie_services():
            return True
        if not self._is_cookie_category_granted(service.category_id.code):
            return False
        return not service.contextual_only

    def _get_blocked_cookie_services(self) -> models.Model:
        """Return the services that must not run for the current request."""
        return self._get_cookie_services().filtered(
            lambda s: not self._is_cookie_service_granted(s)
        )

    def _is_consent_mode_signalled(self) -> bool:
        """Return whether a Google tag may run under the configured mode.

        Never without a key, since the signal is written inside core's key guard.
        Advanced always runs, for its cookieless pings; basic waits until a
        purpose Google serves is granted.
        """
        if not self.google_analytics_key:
            return False
        if self.cookie_consent_mode == 'advanced':
            return True
        state = self._get_consent_mode_state()
        return 'granted' in (state['analytics_storage'], state['ad_storage'])

    def _is_consent_mode_host(self, url: str) -> bool:
        """Return whether a URL belongs to a host Consent Mode governs.

        Only while a tag may run: the exemption exists so that stripping does
        not delete the script the consent state is carried to, and there is
        nothing to carry it to while the tag is held back.
        """
        if not self._is_consent_mode_signalled():
            return False
        host = urlsplit(url or '').hostname or ''
        host = host.lower().removeprefix('www.')
        return any(
            host == known or host.endswith(f'.{known}') for known in CONSENT_MODE_HOSTS
        )

    def _find_cookie_service(
        self, url: str, services: models.Model | None = None
    ) -> models.Model:
        """Return the service claiming a URL, searched among the given set."""
        candidates = self._get_cookie_services() if services is None else services
        for service in candidates:
            if service._matches_url(url):
                return service
        return self.env['muk_website_cookies_consent.service'].browse()

    def _get_consent_mode_state(self) -> dict[str, str]:
        """Return each Consent Mode signal mapped to granted or denied.

        ``security_storage`` is granted unconditionally: it covers
        authentication and fraud prevention, which is strictly necessary.
        """
        granted = set()
        for category in self._get_cookie_categories():
            if self._is_cookie_category_granted(category.code):
                granted.update(category._get_consent_mode_signals())
        granted.add('security_storage')
        return {
            signal: 'granted' if signal in granted else 'denied'
            for signal in CONSENT_MODE_SIGNALS
        }

    def _get_consent_mode_state_json(self) -> Markup:
        """Return the resolved Consent Mode signals as a JSON object.

        Marked safe because it is written into a script element, where QWeb
        would otherwise escape the quotes into entities.
        """
        return Markup(json.dumps(self._get_consent_mode_state()))

    def _get_consent_mode_default_json(self) -> Markup:
        """Return the Consent Mode defaults to emit before any Google tag.

        Before a decision exists everything optional is denied and Google is
        asked to hold its tags for a moment, so a consent given straight away
        is not missed. Once a decision exists the defaults simply state it.
        """
        if self._has_cookie_decision():
            state = self._get_consent_mode_state()
        else:
            state = {
                signal: 'granted' if signal == 'security_storage' else 'denied'
                for signal in CONSENT_MODE_SIGNALS
            }
        return Markup(
            json.dumps({**state, 'wait_for_update': CONSENT_MODE_WAIT_FOR_UPDATE})
        )

    def _get_ads_data_redaction_json(self) -> Markup:
        """Return whether advertising identifiers must be redacted, as JSON.

        Redaction is on for exactly as long as advertising storage is denied.
        """
        state = self._get_consent_mode_state()
        return Markup(json.dumps(state.get('ad_storage') != 'granted'))

    def _get_blocked_third_party_domains_list(self) -> list[str]:
        """Return the hosts the client-side watcher must still block.

        The hosts of still refused services, plus core's unclaimed entries until
        nothing is refused. Consent Mode hosts are exempt on the server's terms,
        or the watcher would block the very tag this module signals to.
        """
        if not self._is_cookie_consent_active() or not self.block_third_party_domains:
            return super()._get_blocked_third_party_domains_list()
        blocked = set()
        for service in self._get_blocked_cookie_services():
            blocked.update(service._get_domain_list())
        if not self._allConsentsGranted():
            claimed = set()
            for service in self._get_cookie_services():
                claimed.update(service._get_domain_list())
            blocked.update(
                set(super()._get_blocked_third_party_domains_list()) - claimed
            )
        if self._is_consent_mode_signalled():
            blocked.difference_update(CONSENT_MODE_HOSTS)
        return sorted(blocked)

    @api.model
    def _get_cookie_compile_fields(self) -> tuple[str, ...]:
        """Return the settings that change what the template compiler decides.

        Whether a static tag is stripped is stored in the template cache, keyed
        on none of these. Kept short: clearing compiled templates is expensive.
        """
        return (
            'cookies_bar',
            'block_third_party_domains',
            'custom_blocked_third_party_domains',
            'google_analytics_key',
            'cookie_consent_mode',
        )

    @api.model
    def _get_cookie_render_fields(self) -> tuple[str, ...]:
        """Return the settings whose value changes what a page renders."""
        return (
            'cookies_bar',
            'block_third_party_domains',
            'google_analytics_key',
            'plausible_shared_key',
            'cookie_layout',
            'cookie_density',
            'cookie_policy_version',
            'cookie_consent_mode',
            'cookie_reopen_float',
            'cookie_policy_id',
        )

    def _get_cookie_render_signature(self) -> str:
        """Return a fingerprint of everything that shapes the rendered markup.

        Folded into the page cache key, so a page built under one configuration
        is never served after another one takes over.
        """
        values = '|'.join(
            str(self[field]) for field in self._get_cookie_render_fields()
        )
        payload = f'{values}|{self._get_cookie_registry_hash()}'
        return hashlib.sha256(payload.encode()).hexdigest()[:REGISTRY_HASH_LENGTH]

    def _get_cookie_banner_version(self) -> str:
        """Return the module version that renders the banner."""
        module = (
            self.env['ir.module.module']
            .sudo()
            .search([('name', '=', 'muk_website_cookies_consent')], limit=1)
        )
        return module.installed_version or ''

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_cookie_scan(self) -> dict:
        """Scan the site now and report what the crawl filed.

        :raise UserError: when not one page of the site could be fetched
        """
        summary = {'pages': 0, 'keys': 0, 'failures': 0, 'running': 0}
        for website in self:
            result = website._scan_cookies()
            for key, value in result.items():
                summary[key] += value
        if not summary['pages'] and summary['running']:
            raise UserError(
                self.env._(
                    'A scan is already running. Its findings appear when it ends.'
                )
            )
        if not summary['pages'] and summary['failures']:
            raise UserError(
                self.env._(
                    'The site could not be reached at %(url)s. A scan fetches '
                    'your own pages over HTTP, so that address has to answer '
                    'from the server Odoo runs on.',
                    url=self[:1].get_base_url(),
                )
            )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': self.env._(
                    '%(pages)s pages scanned, %(keys)s keys on record.',
                    pages=summary['pages'],
                    keys=summary['keys'],
                ),
            },
        }

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    def write(self, vals: dict) -> bool:
        """Write the settings and drop what their old values are baked into.

        Core clears only the default cache, but stripping decisions are stored in
        the template cache, which is keyed on none of these fields.
        """
        result = super().write(vals)
        if set(vals) & set(self._get_cookie_compile_fields()):
            self._clear_cookie_registry_cache()
        return result

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def _render_template(self, template: str, values: dict | None = None) -> str:
        """Render with the visitor's consent state in the template cache key."""
        website = self
        if self._is_cookie_consent_active():
            website = self.with_context(
                cookie_consent_state=self._get_cookie_consent_key()
            )
        return super(Website, website)._render_template(template, values)

    def _allConsentsGranted(self) -> bool:
        """Report full consent only when every optional purpose is granted.

        Overrides the hook core documents for exactly this purpose. Core uses
        the answer to decide whether Google tags may have full consent, which
        must not be true while any purpose is still refused.
        """
        if not self._is_cookie_consent_active():
            return super()._allConsentsGranted()
        granted = self._get_granted_cookie_codes()
        return all(
            category.code in granted
            for category in self._get_optional_cookie_categories()
        )

    def _control_third_party_trackers_in_html(self, html_content: str) -> Markup:
        """Give core's stripping a single root so a pasted snippet survives it.

        Core parses the value as a document, which wraps a pasted snippet in
        ``<html><head>`` and closes the real head early. Wrapping it keeps the
        parse lossless and leaves core the only place deciding what to strip.
        """
        if not html_content or not self._should_remove_third_party_trackers():
            return html_content
        controlled = str(
            super()._control_third_party_trackers_in_html(f'<div>{html_content}</div>')
        )
        return Markup(controlled.removeprefix('<div>').removesuffix('</div>'))

    @memoise_per_request
    def _should_remove_third_party_trackers(self) -> bool:
        """Report whether anything still has to be stripped from the markup.

        Driven by the registry rather than core's single flag, and on while
        anything is refused, for the hosts on core's list no service claims.
        """
        if not self._is_cookie_consent_active() or not self.block_third_party_domains:
            return super()._should_remove_third_party_trackers()
        if self.env.user.has_group('website.group_website_restricted_editor'):
            return False
        return (
            bool(self._get_blocked_cookie_services()) or not self._allConsentsGranted()
        )

    def _is_tag_domains_watchlisted(self, tagName: str, atts: dict) -> bool:
        """Report whether an element belongs to a service that may not run.

        A registry match is final, or core's list would re-block a granted
        service. A Consent Mode host is never stripped: it carries the signal.
        """
        if (
            self._is_cookie_consent_active()
            and self.block_third_party_domains
            and tagName in ('iframe', 'script')
        ):
            src = atts.get('src') or ''
            service = self._find_cookie_service(src)
            if service:
                return not self._is_cookie_service_granted(service)
            if self._is_consent_mode_host(src):
                return False
            if self._allConsentsGranted():
                return False
        return super()._is_tag_domains_watchlisted(tagName, atts)

    def _is_tag_classes_watchlisted(self, tagName: str, atts: dict) -> bool:
        """Release a container whose embed belongs to a granted service.

        Core flags a video block by its class alone, and its own script keeps
        the block collapsed while the flag stands, so an embed allowed in
        place would load into a block of no height.
        """
        if self._is_cookie_consent_active() and self.block_third_party_domains:
            url = (
                atts.get('data-embed-url')
                or atts.get('data-src')
                or atts.get('data-oe-expression')
            )
            service = self._find_cookie_service(url)
            if service and self._is_cookie_service_granted(service):
                return False
        return super()._is_tag_classes_watchlisted(tagName, atts)

    def _remove_third_party_trackers(
        self,
        tagName: str,
        atts: dict,
        cookies_watchlist: list,
    ) -> None:
        """Strip a blocked element and stamp which purpose would release it.

        The stamp is what lets the browser bring back one service when its
        purpose is granted, instead of requiring the blanket consent core's
        own placeholder waits for.
        """
        super()._remove_third_party_trackers(tagName, atts, cookies_watchlist)
        if (
            not self._is_cookie_consent_active()
            or not self.block_third_party_domains
            or not atts.get('data-need-cookies-approval')
        ):
            return
        url = atts.get('data-nocookie-src') or atts.get('src') or ''
        service = self._find_cookie_service(url)
        if service:
            atts['data-muk-cookie-category'] = service.category_id.code
            atts['data-muk-cookie-service'] = service.technical_name
            atts['data-muk-cookie-label'] = service.name
            if service.placeholder_text:
                atts['data-muk-cookie-placeholder'] = service.placeholder_text

    def _get_cookie_scan_urls(self) -> list[str]:
        """Return the pages a scan fetches, the home page first.

        Taken from the sitemap core already builds, so a page reachable by a
        visitor is a page the scan looks at, and a controller that publishes
        itself (a shop, a blog) is covered without knowing about it here.
        """
        self.ensure_one()
        limit = SCAN_PAGE_LIMIT
        urls = ['/']
        policy = self._get_cookie_policy_url()
        if policy.startswith('/'):
            urls.append(policy)
        for page in self._enumerate_pages():
            if len(urls) >= limit:
                break
            location = page.get('loc') or ''
            if location.startswith('/') and location not in urls:
                urls.append(location)
        return urls[:limit]

    def _get_cookie_scan_consent(self) -> str:
        """Return a consent payload granting everything the site declares.

        The scan asks what the site loads when nothing is held back, which is
        the disclosure the registry has to match. Fetched as a refusing visitor
        it would only ever see its own blocking at work.
        """
        self.ensure_one()
        return serialise_state(
            build_state(
                categories=self._get_cookie_categories().mapped('code'),
                services=self._get_cookie_services().mapped('technical_name'),
                policy_version=self.cookie_policy_version,
                registry_hash=self._get_cookie_registry_hash(),
                lang_code=self.default_lang_id.code or '',
            )
        )

    def _get_cookie_scan_hosts(self) -> set[str]:
        """Return the hosts that are the site itself rather than a third party."""
        self.ensure_one()
        hosts = {normalise_host(urlsplit(self.get_base_url()).hostname or '')}
        if self.domain:
            hosts.add(normalise_host(urlsplit(self.domain).hostname or self.domain))
        return {host for host in hosts if host}

    def _lock_cookie_scan(self) -> bool:
        """Take the scan lock for this website, or report it is already taken.

        The cron and a Scan Now click can race to the same rows. An advisory lock
        keeps the second scan out without a row lock held for the whole crawl.
        """
        self.ensure_one()
        self.env.cr.execute(
            'SELECT pg_try_advisory_xact_lock(%s, %s)',
            (SCAN_LOCK_NAMESPACE, self.id),
        )
        return self.env.cr.fetchone()[0]

    def _fetch_cookie_scan_page(self, session, url: str) -> str:
        """Return the markup of one page, or an empty string when it fails."""
        try:
            response = session.get(url, timeout=SCAN_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as error:
            _logger.info('Cookie scan could not fetch %s: %s', url, error)
            return ''
        return response.text

    def _scan_cookies(self) -> dict:
        """Fetch the site's own pages and file what they set and load.

        One session for the whole crawl, so a cookie set on any page is seen.
        :return: counts of pages answered, keys on record and failed pages, and
            whether a scan was already running
        """
        self.ensure_one()
        idle = {'pages': 0, 'keys': 0, 'failures': 0, 'running': 0}
        if not self._lock_cookie_scan():
            _logger.info('A scan of %s is already running.', self.display_name)
            return dict(idle, running=1)
        observations = self.env['muk_website_cookies_consent.observation'].sudo()
        base = self.get_base_url()
        session = requests.Session()
        session.headers['User-Agent'] = SCAN_USER_AGENT
        session.cookies.set(
            CONSENT_COOKIE,
            quote(self._get_cookie_scan_consent()),
            domain=urlsplit(base).hostname,
        )
        own_hosts = self._get_cookie_scan_hosts()
        pages, failures, seen = 0, 0, observations.browse()
        for url in self._get_cookie_scan_urls():
            markup = self._fetch_cookie_scan_page(session, urljoin(base, url))
            if not markup:
                failures += 1
                continue
            pages += 1
            keys = extract_keys(markup, own_hosts, url)
            keys += [
                {'name': cookie.name, 'type': 'http', 'url': url}
                for cookie in session.cookies
            ]
            seen |= observations._record_keys(self, keys)
        self.sudo().write(
            {'cookie_scan_date': fields.Datetime.now(), 'cookie_scan_count': pages}
        )
        return {'pages': pages, 'keys': len(seen), 'failures': failures, 'running': 0}

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.model
    def _cron_scan_cookies(self) -> None:
        """Scan every website whose consent manager is switched on."""
        for website in self.search([]):
            if website._is_cookie_consent_active():
                website._scan_cookies()
