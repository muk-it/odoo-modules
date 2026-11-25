{
    'name': 'MuK MCP Skills',
    'summary': 'Serve skills written in Odoo to Claude and other MCP clients',
    'description': """
        Implements the Skills extension of the Model Context Protocol on top
        of the MuK MCP Server. Administrators write skills in Odoo: a name, a
        line that tells the AI client when to use it, the instructions and
        the files they refer to. Every MCP client that supports the extension
        lists the skills the user of its key may use and loads one when a
        request fits.
    """,
    'version': '17.0.1.0.2',
    'category': 'Tools/API',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/MLmipAWmeSQ',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'muk_mcp',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'views/skill.xml',
        'views/res_config_settings.xml',
        'views/menu.xml',
    ],
    'demo': [
        'demo/skill.xml',
    ],
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
