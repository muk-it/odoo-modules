{
    'name': 'MuK AI Product',
    'summary': 'AI that adds products from links and price lists and writes their texts from facts',
    'description': """
        Adds a Product Content Writer to MuK AI Assistant that adds products
        from web links and vendor price lists, ready to purchase, with skills
        for the product form: find the facts of a product in its own data, its
        documents and on the web, write its name and descriptions from those
        facts only, translate them into every language the company sells in,
        and add image variants as extra images marked as AI-generated. Every
        change waits for approval in the chat.
        Web shop and search texts are filled when eCommerce is installed;
        barcodes and manufacturer data are never generated.
    """,
    'version': '19.0.1.0.2',
    'category': 'Sales/Product',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/R1HyxHaD65M',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'muk_ai_skills',
        'muk_product',
    ],
    'data': [
        'data/ir_model.xml',
        'data/agent.xml',
        'data/skill.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_ai_product/static/src/chat/**/*',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
