{
    'name': 'MuK AI Mistral',
    'summary': 'Mistral AI provider for the MuK AI Assistant',
    'description': '''
        Adds Mistral AI as a first-class provider for muk_ai. Ships the
        full Mistral catalogue pre-seeded with context windows and
        pricing, so the only thing left to configure is your API key.
        Talks to Mistral's stateless Conversations API with live
        streaming, function/tool calling, vision and structured output,
        plus the Mistral built-in connectors — web search, code
        interpreter and image generation — wired to the same capability
        toggles the other muk_ai providers use.
    ''',
    'version': '19.0.1.0.0',
    'category': 'Productivity',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://my.mukit.at/r/f6m',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'muk_ai',
    ],
    'data': [
        'data/provider.xml',
        'data/model.xml',
    ],
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
