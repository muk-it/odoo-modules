from odoo import http


def mcp_route(route=None, **kw):
    kw.update({
        'type': 'mcp',
        'auth': 'mcp',
        'csrf': False,
        'save_session': False,
    })
    return http.route(route=route, **kw)
