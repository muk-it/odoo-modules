from __future__ import annotations

import hashlib
import json
from urllib.parse import urlsplit

from lxml import etree, html
from markupsafe import Markup

from odoo import api, fields, models, tools
from odoo.exceptions import MissingError
from odoo.http import request

from odoo.addons.muk_website_cookies_consent.tools.consent import (
    granted_categories,
    granted_services,
    is_current,
    parse_state,
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
    UNCLASSIFIED_CODE,
)


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

    cookie_blocking = fields.Boolean(
        string='Block Services Before Consent',
        help=(
            'Strip scripts and embeds belonging to a service whose purpose the '
            'visitor has not granted, and replace embeds with a placeholder.'
        ),
        default=True,
    )

    cookie_respect_gpc = fields.Boolean(
        string='Honour Global Privacy Control',
        help=(
            'Treat a Sec-GPC request header as a refusal of every optional '
            'purpose. Its absence never counts as consent.'
        ),
        default=True,
    )

    cookie_publish_gpc_json = fields.Boolean(
        string='Publish /.well-known/gpc.json',
        help=(
            'Declare publicly that this site honours Global Privacy Control. '
            'Only enable it once you have verified that it does.'
        ),
    )

    cookie_consent_mode = fields.Selection(
        selection=[
            ('off', 'Do not signal'),
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

    cookie_log_consent = fields.Boolean(
        string='Record Consent Proof',
        help=(
            'Store every decision so consent can be demonstrated, as GDPR '
            'Art. 7(1) requires.'
        ),
        default=True,
    )

    cookie_log_ip = fields.Boolean(
        string='Record IP Fingerprint',
        help=(
            'Store a salted hash of the truncated visitor IP with each record. '
            'No readable address is kept.'
        ),
        default=True,
    )

    cookie_reopen_footer = fields.Boolean(
        string='Footer Link',
        help='Add a link to the footer so consent can be changed at any time.',
        default=True,
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

    cookie_policy_url = fields.Char(
        string='Policy Link',
        help=(
            'Where the banner sends visitors for the full policy. Leave it '
            'empty to use the page Odoo publishes at /cookie-policy, which '
            'lists your declarations on its own.'
        ),
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
        return self.cookie_policy_url or COOKIE_POLICY_PATH

    @tools.ormcache('self.id')
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
            .sorted(lambda c: (not c.essential, c.sequence, c.id))  # noqa: PLW0108
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

        A purpose that declares neither a cookie nor a service asks for
        permission to do nothing, which is just noise in the dialog.

        ``unclassified`` is held back whatever it holds: a captured key has no
        described purpose yet, and consent cannot be informed when the dialog
        cannot say what it is for. Everything filed there stays refused until
        somebody classifies it, which is the conservative way round.

        Emptiness is judged against this website's own records rather than the
        purpose's one2many, which spans every website: otherwise a global
        purpose whose cookies belong to another site would be offered here.
        """
        populated = self._get_populated_cookie_category_ids()
        return self._get_cookie_categories().filtered(
            lambda c: c.code != UNCLASSIFIED_CODE and (c.essential or c.id in populated)
        )

    @tools.ormcache('self.id')
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

    @tools.ormcache('self.id')
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

    @tools.ormcache('self.id')
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

        Filtered through ``exists()`` because the ids come from a memoised
        list that a deletion in another process can outlive, and declarations
        are the volatile part of the registry now that captures are declared
        into it. One stale id would otherwise raise while the page renders,
        which takes the whole site down over a cookie that was removed. Read
        once per render, so the check costs one query rather than one per
        element.
        """
        return (
            self.env['muk_website_cookies_consent.cookie']
            .sudo()
            .browse(self._get_cookie_declaration_ids())
            .exists()
        )

    @tools.ormcache('self.id')
    def _get_cookie_registry_hash(self) -> str:
        """Return a fingerprint of everything the banner discloses.

        Consent is only as valid as the disclosure it was given against, so a
        new purpose, service, host or declared cookie has to invalidate it.
        Hashing the registry is what makes that automatic instead of relying
        on somebody remembering to raise the policy version.

        Memoised, so the ``exists()`` guards here are paid once per change
        rather than per element, unlike the gating that reads the same lists.
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
        self.env.registry.clear_cache()
        self.env.registry.clear_cache('templates')

    def _is_gpc_requested(self) -> bool:
        """Return whether the request carries a Global Privacy Control signal.

        Only the exact value ``1`` counts; the specification says anything
        else must be ignored.
        """
        if not self.cookie_respect_gpc or not request:
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

        Allowing one embed in place writes a record but answers nothing, so it
        must not silence the banner for the next six months or be filed as a
        refusal of everything else. Payloads written before this flag existed
        count as answered, since they could only come from the banner.
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

    def _get_granted_cookie_codes(self) -> set[str]:
        """Return the purpose codes in force for the current request.

        A Global Privacy Control signal is checked before the stored decision,
        so it also covers a visitor who consented before turning it on. The
        result is narrowed to declared codes: they come from a cookie the
        visitor controls and end up in cache keys, so an unknown one would let
        anybody mint keys and evict everyone else's pages.
        """
        if self._is_gpc_requested():
            return {ESSENTIAL_CODE}
        if not self._has_cookie_decision():
            return {ESSENTIAL_CODE}
        granted = granted_categories(self._get_cookie_state())
        return (granted & self._get_known_cookie_codes()) | {ESSENTIAL_CODE}

    def _get_granted_cookie_services(self) -> set[str]:
        """Return the service names granted for the current request.

        Keyed on the record rather than on an answered decision: allowing an
        embed in place grants that one service without answering anything.
        """
        if not self._has_cookie_record() or self._is_gpc_requested():
            return set()
        known = set(self._get_cookie_services().mapped('technical_name'))
        return granted_services(self._get_cookie_state()) & known

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

        With no key there is no signal on the page, because the consent state
        is written inside core's ``google_analytics_key`` guard, so a tag
        would run against nothing. Advanced is the mode that loads tags before
        any decision, which is the whole point of its cookieless pings. Basic
        promises the opposite, and a refusal is a decision: the tag waits until
        a purpose Google serves is actually granted.
        """
        if self.cookie_consent_mode == 'off' or not self.google_analytics_key:
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

        Core hands its whole static list to the watcher, so one refused
        purpose blocks every listed host. Here the list is the hosts of the
        services that are actually still refused, plus core's own entries that
        no service claims — those stay blocked until nothing is refused, since
        nothing says which purpose they belong to. The hosts Consent Mode
        governs are the exception, and they have to be exempt on exactly the
        terms the server strips by: the watcher rewrites the ``src`` of a
        script created at runtime, which is how a Tag Manager container loads,
        so leaving them here would block the very tag this module signals to.
        """
        if not self._is_cookie_consent_active() or not self.cookie_blocking:
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

        Whether a static tag is stripped is settled while the template
        compiles and stored in the template cache, which is keyed on none of
        these. Everything else here shapes the rendered values instead, and
        those already ride on the page cache signature, so this stays as short
        as it can be: clearing compiled templates is expensive.
        """
        return (
            'cookies_bar',
            'block_third_party_domains',
            'custom_blocked_third_party_domains',
            'google_analytics_key',
            'cookie_blocking',
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
            'cookie_blocking',
            'cookie_respect_gpc',
            'cookie_consent_mode',
            'cookie_log_consent',
            'cookie_reopen_footer',
            'cookie_reopen_float',
        )

    def _get_cookie_render_signature(self) -> str:
        """Return a fingerprint of everything that shapes the rendered markup.

        Odoo caches whole pages and its key describes the request, not the
        configuration behind the response. Folding the settings and the registry
        into the key is what keeps a page built under one configuration from
        being served after another one takes over.
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
    # ORM
    # ----------------------------------------------------------

    def write(self, vals: dict) -> bool:
        """Write the settings and drop what their old values are baked into.

        Core clears only the default cache, but whether a static tag is
        stripped is decided while the template compiles and stored in the
        template cache, which is keyed on none of these fields. Without this a
        tag kept under one setting keeps being served after the setting that
        kept it is turned off.
        """
        result = super().write(vals)
        if set(vals) & set(self._get_cookie_compile_fields()):
            self._clear_cookie_registry_cache()
        return result

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    def _allConsentsGranted(self) -> bool:  # noqa: N802
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
        """Strip the blocked third-party tags out of a stored HTML value.

        Core parses the value as a document, which only survives when it holds
        exactly one root element. What an admin pastes into the custom head or
        footer code is a snippet — typically a comment followed by a script —
        and parsing that as a document wraps it in ``<html><head>`` and drops
        the leading comment. Injected into the real head, that closes it early
        and the rest of the page is left to the browser's error recovery.
        Parsed as fragments instead, so what was pasted is what is served,
        minus the tags whose purpose the visitor has not granted.
        """
        if not html_content or not self._should_remove_third_party_trackers():
            return html_content
        try:
            fragments = html.fragments_fromstring(str(html_content))
        except (etree.ParserError, etree.XMLSyntaxError):
            return html_content
        rendered = []
        for fragment in fragments:
            if isinstance(fragment, str):
                rendered.append(fragment)
                continue
            for element in fragment.iter('script', 'iframe'):
                self._remove_third_party_trackers(
                    element.tag, element.attrib, ['domains']
                )
            rendered.append(html.tostring(fragment, encoding='unicode'))
        return Markup(''.join(rendered))

    def _should_remove_third_party_trackers(self) -> bool:
        """Report whether anything still has to be stripped from the markup.

        Core answers this all-or-nothing on a single optional flag. Here it is
        driven by the registry, so stripping stops for a service as soon as its
        own purpose is granted. It also stays on while anything is refused, to
        cover the hosts on core's list that no service claims a purpose for.
        """
        if not self._is_cookie_consent_active() or not self.cookie_blocking:
            return super()._should_remove_third_party_trackers()
        if self.env.user.has_group('website.group_website_restricted_editor'):
            return False
        return (
            bool(self._get_blocked_cookie_services()) or not self._allConsentsGranted()
        )

    def _is_tag_domains_watchlisted(self, tagName: str, atts: dict) -> bool:  # noqa: N803
        """Report whether an element belongs to a service that may not run.

        When the registry claims the host, its answer is final: core's static
        list names the same hosts and knows nothing about purposes, so falling
        back to it would re-block a service just granted. A Consent Mode host
        is never stripped, since removing the tag would delete the very script
        that carries the signal.
        """
        if (
            self._is_cookie_consent_active()
            and self.cookie_blocking
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

    def _remove_third_party_trackers(
        self,
        tagName: str,
        atts: dict,
        cookies_watchlist: list,  # noqa: N803
    ) -> None:
        """Strip a blocked element and stamp which purpose would release it.

        The stamp is what lets the browser bring back one service when its
        purpose is granted, instead of requiring the blanket consent core's
        own placeholder waits for.
        """
        super()._remove_third_party_trackers(tagName, atts, cookies_watchlist)
        if (
            not self._is_cookie_consent_active()
            or not self.cookie_blocking
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
