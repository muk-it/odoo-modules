{
    'name': 'MuK AI Decision',
    'summary': 'Fast typed decisions for MuK AI: choices, scores and yes/no answers',
    'description': """
        Adds decision models to the MuK AI assistant. A decision model reads
        a text or a record and answers typed questions: one choice out of a
        list, a score on a scale, or the probability of a yes, each with its
        confidence. One service answers them for every module, through any
        server speaking the System One API, TypeSafe Jev in the cloud or a
        self-hosted Laya, or a small chat model of an existing provider.
        Every decision is logged with its model, answers, duration and cost.
        A Decide with AI server action fills fields, routes records to other
        actions and flags unsure ones from any automation rule or scheduled
        action, a decision step in front of an agent starts its chats only
        where they are needed, and agents decide about texts or records
        through the decide tool.
    """,
    'version': '18.0.1.3.1',
    'category': 'Productivity',
    'license': 'LGPL-3',
    'author': 'MuK IT',
    'website': 'http://www.mukit.at',
    'live_test_url': 'https://youtu.be/05VsEYsSOT4',
    'contributors': [
        'Mathias Markl <mathias.markl@mukit.at>',
    ],
    'depends': [
        'muk_ai_automation',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/provider.xml',
        'data/model.xml',
        'views/ai_model.xml',
        'views/ai_provider.xml',
        'views/base_automation.xml',
        'views/decision_log.xml',
        'views/ir_actions_server.xml',
        'views/menu.xml',
    ],
    'demo': [
        'demo/res_partner.xml',
        'demo/ir_actions_server.xml',
        'demo/base_automation.xml',
        'demo/decision_log.xml',
    ],
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
