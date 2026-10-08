import { expect, press, queryAllTexts, runAllTimers, test } from '@odoo/hoot';
import {
    contains,
    getService,
    MockServer,
    mountWebClient,
    patchWithCleanup,
} from '@web/../tests/web_test_helpers';
import { ActionPlugin } from '@web/webclient/actions/action_plugin';

import { defineAIModels } from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();

async function searchChats() {
    await press(['control', 'k']);
    await contains('.o_command_palette_search input').edit('# Alp ', {
        confirm: false,
    });
    await runAllTimers();
}

test.tags('desktop');
test('the # palette searches the chats, opens one and starts one named by the search', async () => {
    await mountWebClient();
    MockServer.env['muk_ai.session'].create([
        { name: 'Alpha report', create_date: '2026-01-01 10:00:00' },
        { name: 'Beta', create_date: '2026-01-02 10:00:00' },
        { name: 'Alpine trip', create_date: '2026-01-03 10:00:00' },
    ]);
    const opened = [];
    patchWithCleanup(getService(ActionPlugin), {
        doAction: (action) => {
            opened.push(action.params);
        },
    });
    await searchChats();
    expect('.o_command_palette_search input').toHaveAttribute(
        'placeholder',
        'Search MuK AI chats...',
    );
    expect(queryAllTexts('.o_command_name')).toEqual([
        'New Chat',
        'Alpine trip',
        'Alpha report',
    ]);
    await contains('.o_command:contains(Alpine trip)').click();
    await searchChats();
    await contains('.o_command:contains(New Chat)').click();
    await runAllTimers();
    expect(opened).toEqual([{ session_id: 5 }, { session_id: 6 }]);
    expect(MockServer.env['muk_ai.session'].read([6], ['name'])[0].name).toBe('Alp');
});
