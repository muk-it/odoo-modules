{
    'name': 'MuK Check',
    'summary': 'Check security settings, the Odoo version and app updates',
    'description': """
        This module checks a database against editable rules: security settings,
        exposed pages, the Odoo version, new store versions and apps that need
        a database upgrade. It reports what it finds and changes nothing on its
        own. Rules can be changed in the browser and added by other modules.
    """,
    'version': '20.0.1.0.4',
    'category': 'Tools/Utils',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/ivoHbm_H22Q',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'base_import_module',
        'base_setup',
        'mail',
    ],
    'data': [
        'security/ir.access.csv',
        'data/ir_config_parameter.xml',
        'data/ir_actions_server.xml',
        'data/ir_cron.xml',
        'templates/message_findings.xml',
        'views/ir_module_module.xml',
        'views/check_finding.xml',
        'views/check_rule.xml',
        'views/check_run.xml',
        'views/res_config_settings.xml',
        'views/menu.xml',
        'data/check_rule.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'muk_check/static/src/check/overview/overview.scss',
            'muk_check/static/src/check/updates/updates.scss',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
