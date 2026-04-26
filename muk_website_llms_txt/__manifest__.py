{
    'name': 'MuK LLMs TXT & Markdown',
    'summary': 'Serve llms.txt and markdown content for AI agents',
    'description': '''
        Make your Odoo website AI-ready by implementing the llms.txt
        standard and Cloudflare-style markdown content negotiation.
        AI agents and crawlers can discover your content via /llms.txt
        and request any page as clean markdown via the Accept header.
    ''',
    'version': '19.0.1.0.4',
    'category': 'Website/SEO',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/k111jogE3LA',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'website',
    ],
    'data': [
        'views/res_config_settings.xml',
    ],
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
