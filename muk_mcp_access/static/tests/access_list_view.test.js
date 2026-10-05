import { describe, expect, test } from '@odoo/hoot';
import { animationFrame } from '@odoo/hoot-mock';
import {
    contains,
    defineModels,
    fields,
    mockService,
    MockServer,
    models,
    mountView,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import '@muk_mcp_access/views/list/access_list_view';

describe.current.tags('muk_mcp_access');

class McpAccess extends models.Model {
    _name = 'mcp.access';
    allow_write = fields.Boolean();
    _records = [{ id: 1, allow_write: false }];
}

defineMailModels();
defineModels({ McpAccess });

const ARCH = `
    <list editable="bottom" js_class="mcp_access_list">
        <field name="allow_write"/>
    </list>`;

/**
 * Mount the MCP access list and capture the actions requested through the
 * action service, which adds an entry and closes at once.
 *
 * @param {string} [arch] the list arch to mount
 * @returns {Promise<any[]>} the actions passed to ``doAction``, in order
 */
async function mountAccessList(arch = ARCH) {
    const actions = [];
    mockService('action', {
        doAction: (action, options) => {
            actions.push(action);
            MockServer.env['mcp.access'].create({ allow_write: true });
            options.onClose();
            return Promise.resolve();
        },
    });
    await mountView({ type: 'list', resModel: 'mcp.access', arch });
    return actions;
}

test('the access list keeps the standard buttons and adds Add Models', async () => {
    await mountAccessList();
    expect('.o_control_panel_main_buttons button:contains(Add Models)').toHaveCount(1);
    expect('.o_control_panel_main_buttons .o_list_button_add').toHaveCount(1);
});

test('the Add Models button opens the wizard and reloads the list when it closes', async () => {
    const actions = await mountAccessList();
    expect('.o_data_row').toHaveCount(1);
    await contains('.o_control_panel_main_buttons button:contains(Add Models)').click();
    await animationFrame();
    expect(actions).toEqual(['muk_mcp_access.action_model_selection']);
    expect('.o_data_row').toHaveCount(2);
});

test('a plain list view does not get the Add Models button', async () => {
    await mountAccessList(`
        <list editable="bottom">
            <field name="allow_write"/>
        </list>`);
    expect('button:contains(Add Models)').toHaveCount(0);
    expect('.o_control_panel_main_buttons .o_list_button_add').toHaveCount(1);
});
