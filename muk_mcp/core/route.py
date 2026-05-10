from odoo import http


def mcp_route(route=None, **kw):
    kw.setdefault('cors', '*')
    kw.update({
        'type': 'mcp',
        'auth': 'mcp',
        'csrf': False,
        'save_session': False,
    })
    return http.route(route=route, **kw)
