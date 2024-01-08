{
    'name': 'MuK Product', 
    'summary': 'Centralize your product views',
    'description': '''
        This module gives you a quick view of all your products, 
        accessible from your home menu.
    ''',
    'version': '17.0.1.1.0', 
    'category': 'Sales/Sales',
    'license': 'LGPL-3', 
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://mukit.at/demo',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'base_setup',
        'product',
        'uom',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/product_template.xml',
        'views/product_search.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_product/static/src/views/**/*.*',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
