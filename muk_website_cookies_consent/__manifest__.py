{
    'name': 'MuK Cookie Consent',
    'summary': 'Granular cookie consent manager with per-service blocking and consent proof',
    'description': """
        Replaces the built-in cookies bar with a real consent manager.
        Visitors consent per purpose instead of all-or-nothing, every
        decision is recorded as proof, third-party scripts and embeds are
        blocked per service until their category is granted, and Google
        Consent Mode v2 is signalled automatically.
    """,
    'version': '16.0.1.1.0',
    'category': 'Website/Website',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'website',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/category.xml',
        'data/geo_rule.xml',
        'data/service.xml',
        'data/cookie.xml',
        'data/ir_cron.xml',
        'views/category.xml',
        'views/service.xml',
        'views/cookie.xml',
        'views/observation.xml',
        'views/consent.xml',
        'views/geo_rule.xml',
        'views/menu.xml',
        'views/res_config_settings.xml',
        'views/snippets.xml',
        'templates/cookies_bar.xml',
        'templates/cookie_policy.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'muk_website_cookies_consent/static/src/snippets/cookies_banner/**/*',
            'muk_website_cookies_consent/static/src/snippets/cookies_approval/**/*',
            'muk_website_cookies_consent/static/src/snippets/cookies_observer/**/*',
        ],
        'website.assets_wysiwyg': [
            'muk_website_cookies_consent/static/src/snippets/cookies_bar_option/**/*',
        ],
        'web.assets_tests': [
            'muk_website_cookies_consent/static/tests/tours/**/*',
        ],
        'web.qunit_suite_tests': [
            'muk_website_cookies_consent/static/src/snippets/cookies_banner/consent_state.js',
            'muk_website_cookies_consent/static/tests/snippets/**/*_tests.js',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
