{
    'name': 'MuK MCP OAuth',
    'summary': 'OAuth 2.1 authorization server for the MCP endpoint',
    'description': """
        Adds an OAuth 2.1 authorization server on top of the MCP endpoint,
        enabling the zero-config custom connector experience on claude.ai
        web and mobile apps: add the URL, log in to Odoo, authorize. Each
        access token is materialized as an MCP key, so scope gating, rate
        limiting and audit logging keep working unchanged.
    """,
    'version': '19.0.1.0.0',
    'category': 'Tools/API',
    'license': 'LGPL-3',
    'author': 'MuK IT, Jarsa',
    'website': 'http://www.mukit.at',
    'contributors': [
        'Jesús Alan Ramos Rodríguez <alan.ramos@jarsa.com>',
    ],
    'depends': [
        'muk_mcp',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'data/ir_config_parameter_data.xml',
        'data/ir_cron_data.xml',
        'views/oauth_templates.xml',
        'views/res_users_views.xml',
        'views/connect.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
