{
    'name': 'MuK Contacts', 
    'summary': 'Improves the contact app',
    'description': '''
        This module improves and extends the contact app
        and the related partner model.
    ''',
    'version': '18.0.1.0.1', 
    'category': 'Sales/CRM',
    'license': 'LGPL-3', 
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://my.mukit.at/r/f6m',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'mail',
        'base_vat',
        'contacts',
        'muk_web_utils',
    ],
    'data': [
        'data/ir_sequence.xml',
        'templates/ir_qweb_widget.xml',
        'views/res_partner.xml',
    ],
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
