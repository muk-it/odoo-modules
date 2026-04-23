{
    'name': 'MuK AI — Agentidoo Connector',
    'summary': 'Route muk_ai chat through the Agentidoo platform (AAP v1).',
    'description': '''
        Adds Agentidoo as a provider to muk_ai and ships an in-Odoo
        onboarding wizard that registers the Odoo instance with the
        Agentidoo API. Speaks AAP v1 (Agentidoo Agent Protocol v1) over
        https://api.agentidoo.com. Requires an Agentidoo API key obtained
        at https://agentidoo.com.
    ''',
    'version': '19.0.1.4.3',
    'category': 'Custom/Agentidoo',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'depends': [
        'muk_ai',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/provider.xml',
        'wizards/onboarding_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
}
