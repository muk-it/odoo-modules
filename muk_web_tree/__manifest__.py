{
    'name': 'MuK Tree List',
    'summary': 'Adds a tree list view for hierarchical records',
    'description': """
        The module adds the treelist view type: a list view whose rows nest
        under their parent record and open and close like the folders of a
        file explorer. It works on any model with a many2one to itself, such
        as product categories, contacts, departments or locations, and keeps
        what a list view offers: inline editing, optional columns, sums,
        widgets and decorations.
    """,
    'version': '20.0.1.0.4',
    'category': 'Tools/UI',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/FFZvYAT0uQo',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'base_import',
        'muk_web_group',
        'muk_web_refresh',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_web_tree/static/src/**/*',
        ],
        'web.assets_unit_tests': [
            'muk_web_tree/static/tests/**/*',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
