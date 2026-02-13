{
    'name': 'MuK Product', 
    'summary': 'Centralize your product views',
    'description': '''
        This module gives you a quick view of all your products, 
        accessible from your home menu.
    ''',
    'version': '19.0.1.4.1',
    'category': 'Sales/Product',
    'license': 'LGPL-3', 
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://my.mukit.at/r/f6m',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'base_setup',
        'product',
        'muk_web_utils',
    ],
    'data': [
        'data/ir_sequence.xml',
        'security/ir.model.access.csv',
        'views/product_template.xml',
        'views/product_product.xml',
        'views/product_document.xml',
        'views/product_pricelist_item.xml',
        'views/res_config_settings.xml',
        'views/product_search.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_product/static/src/views/**/*.*',
        ],
        'web.assets_unit_tests': [
            'muk_product/static/tests/**/*.test.js',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
