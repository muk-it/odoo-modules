{
    'name': 'MuK Contacts',
    'summary': 'Improves the contact app',
    'description': """
        This module improves and extends the contact app
        and the related partner model.
    """,
    'version': '20.0.1.3.1',
    'category': 'Sales/CRM',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'support': 'support@mukit.at',
    'live_test_url': 'https://youtu.be/w4n6-NtSR70',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'base_setup',
        'contacts',
        'mail',
        'muk_web_utils',
        'muk_web_tree',
    ],
    'data': [
        'data/ir_sequence.xml',
        'templates/ir_qweb_widget.xml',
        'views/res_partner.xml',
        'views/res_config_settings.xml',
        'views/base_partner_merge.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_contacts/static/src/views/**/*.*',
        ],
        'web.assets_unit_tests': [
            'muk_contacts/static/tests/**/*.test.js',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
