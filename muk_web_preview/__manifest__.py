{
    'name': 'MuK Preview',
    'summary': 'Preview reports, emails, Outlook messages, CSV tables and Office files',
    'description': """
        Extends the file viewer and the attachment thumbnails with previews
        for email files (.eml), Outlook messages (.msg), CSV and TSV tables
        and source code. Remote images in emails stay blocked until they are
        loaded on demand. Word, Excel and PowerPoint files can be opened with
        the Microsoft Office Online viewer. Reports open from the print menu
        in the file viewer instead of downloading, and downloaded reports can
        open in a new browser tab as well.
    """,
    'version': '20.0.1.2.0',
    'category': 'Tools/Utils',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/_EZG9yqAG7w',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'mail',
    ],
    'data': [
        'views/res_config_settings.xml',
        'templates/preview_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            (
                'after',
                'web/static/src/core/file_viewer/file_model.js',
                'muk_web_preview/static/src/core/file_viewer/file_model.js',
            ),
            (
                'after',
                'web/static/src/core/file_viewer/file_viewer.js',
                'muk_web_preview/static/src/core/file_viewer/file_viewer.js',
            ),
            (
                'after',
                'web/static/src/core/file_viewer/file_viewer.xml',
                'muk_web_preview/static/src/core/file_viewer/file_viewer.xml',
            ),
            'muk_web_preview/static/src/report/**/*',
        ],
        'muk_web_preview.assets_preview': [
            'muk_web_preview/static/src/preview/content/content.scss',
        ],
        'web.assets_unit_tests': [
            'muk_web_preview/static/tests/**/*',
        ],
    },
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
