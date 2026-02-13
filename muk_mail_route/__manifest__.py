{
    'name': 'MuK Mail Routing', 
    'summary': 'Collects unrouted and failed emails',
    'description': '''
        This module collects mails that could not be routed 
        and allows them to be assigned subsequently.
    ''',
    'version': '19.0.1.1.0',
    'category': 'Productivity/Mail',
    'license': 'LGPL-3', 
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://my.mukit.at/r/f6m',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'mail',
        'muk_mail_utils',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/mail_mail.xml',
        'views/mail_message.xml',
        'views/configuration.xml',
        'views/container.xml',
        'views/router.xml',
        'views/menu.xml',
    ],
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
