{
    'name': 'MuK Contacts vCard', 
    'summary': 'Extends the vCard export with extra fields',
    'description': '''
        This module extends the vCard export to include more detailed 
        contact information. Furthermore, it improves the contact view.
    ''',
    'version': '19.0.1.1.0',
    'category': 'Sales/CRM',
    'license': 'LGPL-3', 
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/j_iZRgJnOGk',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'base_vat',
        'muk_contacts',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/res_partner.xml',
        'views/honorific.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_contacts_vcard/static/src/**/*',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'post_init_hook': '_setup_module',
}
