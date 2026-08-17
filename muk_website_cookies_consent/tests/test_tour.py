import time

from odoo.tests import HttpCase, tagged

from odoo.addons.muk_website_cookies_consent.tools.consent import (
    build_state,
    serialise_state,
)
from odoo.addons.muk_website_cookies_consent.tools.constants import CONSENT_COOKIE

EMBED_PATH = '/muk-cookies-embed'

RENDER_TIMEOUT = 120


@tagged('post_install', '-at_install')
class TestCookieTours(HttpCase):
    """The consent flows a visitor actually walks through."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.website = cls.env['website'].search([], limit=1)
        cls.website.write(
            {
                'cookies_bar': True,
                'block_third_party_domains': True,
                'cookie_layout': 'bar_bottom',
                'cookie_density': 'full',
                'cookie_reopen_footer': True,
                'cookie_reopen_float': 'right',
            }
        )
        cls.publish_embed_page()

    @classmethod
    def publish_embed_page(cls) -> None:
        """Publish a page carrying a third-party video embed.

        The embed lives on a page of its own because the blocking path it
        exercises only exists for markup a visitor receives, not for the
        editor's own preview.
        """
        view = cls.env['ir.ui.view'].create(
            {
                'name': 'Cookie Embed Test',
                'type': 'qweb',
                'key': 'muk_website_cookies_consent.embed_test',
                'website_id': cls.website.id,
                'arch': """
                    <t name="Cookie Embed Test" t-name="muk_website_cookies_consent.embed_test">
                        <t t-call="website.layout">
                            <div id="wrap" class="oe_structure">
                                <section class="s_text_block pt64 pb64">
                                    <div class="container">
                                        <div class="media_iframe_video">
                                            <div class="media_iframe_video_size"/>
                                            <iframe class="o_iframe" frameborder="0"
                                                src="https://www.youtube.com/embed/dQw4w9WgXcQ"/>
                                        </div>
                                    </div>
                                </section>
                            </div>
                        </t>
                    </t>
                """,
            }
        )
        cls.env['website.page'].create(
            {
                'view_id': view.id,
                'url': EMBED_PATH,
                'website_id': cls.website.id,
                'is_published': True,
            }
        )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def warm_render(
        self, path: str, codes: list[str], services: list[str] | None = None
    ) -> None:
        """Render a page once under a decision a tour is about to take.

        Every distinct decision is a deliberate cache miss, so the page a tour
        reloads into would otherwise be rendered from cold while the twenty
        seconds a tour allows for that reload are running out.

        :param path: the path the tour reloads
        :param codes: the purpose codes the decision grants
        :param services: the service names the decision grants
        """
        state = build_state(
            categories=codes,
            services=services or [],
            policy_version=self.website.cookie_policy_version,
            registry_hash=self.website._get_cookie_registry_hash(),
            lang_code='en_US',
            consent_uid='warm-up',
            timestamp=int(time.time()),
        )
        self.opener.cookies.set(CONSENT_COOKIE, serialise_state(state))
        try:
            self.url_open(path, timeout=RENDER_TIMEOUT)
        finally:
            self.opener.cookies.pop(CONSENT_COOKIE, None)

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_refuse_all_from_the_first_layer(self):
        self.warm_render('/', ['essential'])
        self.start_tour('/', 'muk_cookies_reject_all', timeout=180)

    def test_accept_all_from_the_first_layer(self):
        offered = self.website._get_offered_cookie_categories().mapped('code')
        self.warm_render('/', offered)
        self.start_tour('/', 'muk_cookies_accept_all', timeout=180)

    def test_choose_one_purpose_in_the_preference_centre(self):
        self.warm_render('/', ['essential', 'analytics'])
        self.start_tour('/', 'muk_cookies_customise', timeout=180)

    def test_navigating_between_the_two_layers(self):
        self.warm_render('/', ['essential'])
        self.start_tour('/', 'muk_cookies_layers', timeout=180)

    def test_allowing_a_single_embed_where_it_stands(self):
        self.warm_render(EMBED_PATH, ['essential'])
        self.warm_render(EMBED_PATH, ['essential'], ['youtube'])
        self.start_tour(EMBED_PATH, 'muk_cookies_embed', timeout=180)

    def test_setting_the_banner_layout_from_the_editor(self):
        self.website.write(
            {
                'cookie_layout': 'bar_bottom',
                'cookie_density': 'full',
                'cookie_reopen_footer': True,
                'cookie_reopen_float': 'right',
            }
        )
        self.start_tour(
            '/odoo/website', 'muk_cookies_builder', login='admin', timeout=300
        )

    def test_refusing_clears_the_cookies_it_refused(self):
        self.warm_render('/', ['essential'])
        self.start_tour('/', 'muk_cookies_clearing', timeout=180)
