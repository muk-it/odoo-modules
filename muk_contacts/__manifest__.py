{
    'name': 'MuK Contacts',
    'summary': 'Improves the contact app',
    'description': """
        This module improves and extends the contact app
        and the related partner model.
    """,
    'version': '19.0.1.1.14',
    'category': 'Sales/CRM',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/UE_owy582jY',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'base_setup',
        'contacts',
        'mail',
        'muk_web_utils',
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
            (
                'after',
                'web/static/src/views/fields/relational_utils.js',
                'muk_contacts/static/src/js/partner_many2one.js',
            ),
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
