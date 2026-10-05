{
    'name': 'MuK Calendar',
    'summary': 'Record sync and iCal sharing for the calendar app',
    'description': """
        This module improves and extends the calendar app. A calendar can
        show the records of any model on one of their dates, such as task
        deadlines or scheduled deliveries, and follows every change to them.
        Any calendar can be shared as a secret iCal link to subscribe to it
        from Google, Apple or Outlook.
    """,
    'version': '20.0.1.0.0',
    'category': 'Productivity/Calendar',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/p0gxzsE_dgg',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'calendar',
        'base_automation',
    ],
    'data': [
        'data/ir_cron.xml',
        'views/calendar_calendar.xml',
    ],
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'uninstall_hook': '_uninstall_hook',
}
