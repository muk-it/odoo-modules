from __future__ import annotations

import re

from lxml import html

from odoo.tests import HttpCase, tagged

RENDER_TIMEOUT = 120

LAYOUTS = ('bar_bottom', 'bar_top', 'box_left', 'box_right', 'center')
DENSITIES = ('full', 'compact')

INTERACTION_SELECTORS = (
    '.mk_cookies_accept_all',
    '.mk_cookies_reject_all',
    '#muk_cookies_customize',
    '#muk_cookies_dismiss',
    '#muk_cookies_back',
    '#muk_cookies_save',
    "[data-layer='notice']",
    "[data-layer='preferences']",
    "input[name='muk_cookie_category']",
    '[data-muk-cookie-name]',
    '[data-muk-service]',
)

ROOT_ATTRIBUTES = (
    'data-muk-cookie-ask',
    'data-muk-cookie-pv',
    'data-muk-cookie-rh',
    'data-muk-cookie-days',
    'data-muk-cookie-log',
)


@tagged('post_install', '-at_install')
class TestBannerContract(HttpCase):
    """The invariants every banner layout has to keep, whatever it looks like.

    The interaction is bound to selectors and the compliance claim rests on
    what the first layer offers, so both are asserted against the served
    markup rather than trusted to survive a template edit.
    """

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.website = cls.env['website'].search([], limit=1)
        cls.website.write({'cookies_bar': True, 'block_third_party_domains': True})

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def banner_of(self, layout: str, density: str = 'full') -> html.HtmlElement:
        """Return the served banner element for a layout and density.

        :param layout: a value of the website's ``cookie_layout`` field
        :param density: a value of the website's ``cookie_density`` field
        :return: the parsed ``#website_cookies_bar`` element
        """
        self.website.cookie_density = density
        self.website.cookie_layout = layout
        body = self.url_open('/', timeout=RENDER_TIMEOUT).text
        tree = html.fromstring(body)
        found = tree.xpath("//*[@id='website_cookies_bar']")
        self.assertTrue(found, f'No banner was served for the {layout} layout.')
        return found[0]

    def button_weight(self, button: html.HtmlElement) -> set[str]:
        """Return the Bootstrap variant and size classes of a button."""
        classes = set(button.get('class', '').split())
        return {
            name
            for name in classes
            if re.fullmatch(r'btn-(?!.*(?:muk|cookies))[a-z0-9-]+', name)
        }

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_every_layout_keeps_the_interaction_contract(self):
        for layout in LAYOUTS:
            banner = self.banner_of(layout)
            for selector in INTERACTION_SELECTORS:
                self.assertTrue(
                    banner.cssselect(selector),
                    f'The {layout} layout is missing {selector}, which the '
                    f'banner interaction binds to.',
                )

    def test_every_layout_carries_the_state_the_browser_needs(self):
        for layout in LAYOUTS:
            banner = self.banner_of(layout)
            for attribute in ROOT_ATTRIBUTES:
                self.assertIn(
                    attribute,
                    banner.attrib,
                    f'The {layout} layout drops {attribute}, so a decision '
                    f'could not be stored against the current disclosure.',
                )

    def test_every_layout_offers_both_choices_at_equal_weight(self):
        for layout in LAYOUTS:
            banner = self.banner_of(layout)
            notice = banner.cssselect("[data-layer='notice']")[0]
            accept = notice.cssselect('.mk_cookies_accept_all')
            reject = notice.cssselect('.mk_cookies_reject_all')
            self.assertTrue(accept, f'{layout}: accept is not on the first layer.')
            self.assertTrue(reject, f'{layout}: refuse is not on the first layer.')
            self.assertEqual(
                self.button_weight(accept[0]),
                self.button_weight(reject[0]),
                f'{layout}: accept and refuse must share one variant and size, '
                f'or the banner nudges the visitor.',
            )

    def test_no_layout_pre_ticks_an_optional_purpose(self):
        for layout in LAYOUTS:
            banner = self.banner_of(layout)
            for box in banner.cssselect("input[name='muk_cookie_category']"):
                if box.get('disabled') is not None:
                    continue
                self.assertIsNone(
                    box.get('checked'),
                    f'{layout}: "{box.get("value")}" is pre-ticked, and consent '
                    f'given through a pre-ticked box is not consent.',
                )

    def test_every_layout_is_announced_as_a_dialog(self):
        for layout in LAYOUTS:
            banner = self.banner_of(layout)
            dialog = banner.cssselect("[role='dialog']")
            self.assertTrue(dialog, f'{layout}: the banner is not a dialog.')
            labelled_by = dialog[0].get('aria-labelledby')
            self.assertTrue(labelled_by, f'{layout}: the dialog has no label.')
            self.assertTrue(
                banner.cssselect(f'#{labelled_by}'),
                f'{layout}: aria-labelledby points at "{labelled_by}", which is '
                f'not in the banner.',
            )

    def test_the_registry_driven_markup_is_never_editable(self):
        banner = self.banner_of('bar_bottom')
        for el in banner.cssselect('.oe_structure'):
            self.assertFalse(
                el.cssselect('[data-muk-cookie-name], [data-muk-service]')
                or el.cssselect("input[name='muk_cookie_category']"),
                'Saving an editable region freezes its rendered children, so '
                'registry-driven markup must stay outside oe_structure or the '
                'disclosure drifts from the hash consent is checked against.',
            )

    def test_the_preference_centre_cannot_be_edited_away(self):
        banner = self.banner_of('bar_bottom')
        preferences = banner.cssselect("[data-layer='preferences']")[0]
        self.assertEqual(preferences.get('data-oe-protected'), 'true')
        self.assertIn('o_not_editable', preferences.get('class', ''))

    def test_the_layout_reaches_the_markup(self):
        for layout in LAYOUTS:
            banner = self.banner_of(layout)
            self.assertTrue(
                banner.cssselect(f'.mk_cookies_{layout}'),
                f'{layout}: the builder selects layouts by this class, so the '
                f'server has to render it.',
            )

    def test_every_density_keeps_the_contract(self):
        for density in DENSITIES:
            banner = self.banner_of('bar_bottom', density)
            for selector in INTERACTION_SELECTORS:
                self.assertTrue(
                    banner.cssselect(selector),
                    f'The {density} density is missing {selector}.',
                )
            notice = banner.cssselect("[data-layer='notice']")[0]
            accept = notice.cssselect('.mk_cookies_accept_all')[0]
            reject = notice.cssselect('.mk_cookies_reject_all')[0]
            self.assertEqual(
                self.button_weight(accept),
                self.button_weight(reject),
                f'{density}: the two choices must stay equal in weight.',
            )

    def test_every_density_keeps_the_dialog_named(self):
        for density in DENSITIES:
            banner = self.banner_of('bar_bottom', density)
            dialog = banner.cssselect("[role='dialog']")[0]
            labelled_by = dialog.get('aria-labelledby')
            self.assertTrue(
                banner.cssselect(f'#{labelled_by}'),
                f'{density}: the dialog name must survive, even when hidden.',
            )

    def test_a_density_never_changes_what_the_visitor_is_told(self):
        told = {}
        for density in DENSITIES:
            banner = self.banner_of('bar_bottom', density)
            paragraph = banner.cssselect('.mk_cookies_text')[0]
            told[density] = ' '.join(paragraph.text_content().split())
        self.assertEqual(
            told['full'],
            told['compact'],
            'Density is a matter of taste; the disclosure is not.',
        )
