import { expect, queryAllTexts, test, waitFor } from '@odoo/hoot';
import {
    contains,
    fields,
    getService,
    MockServer,
    models,
    mountWebClient,
} from '@web/../tests/web_test_helpers';
import { ActionPlugin } from '@web/webclient/actions/action_plugin';

import { defineAIModels } from '@muk_ai/../tests/muk_ai_test_helpers';

class PromptModel extends models.Model {
    _name = 'muk_ai.test_prompt';
    instructions = fields.Text();
    prompt_history_metadata = fields.Json();
    _records = [
        {
            id: 1,
            instructions: 'Be brief.',
            prompt_history_metadata: {
                instructions: [
                    {
                        create_date: '2026-01-02 10:00:00',
                        create_user_name: 'Mitchell Admin',
                    },
                    {
                        create_date: '2026-01-01 10:00:00',
                        create_user_name: 'Marc Demo',
                    },
                ],
            },
        },
        { id: 2, instructions: 'New.', prompt_history_metadata: {} },
    ];
    prompt_history_unified_diff(id, field, index) {
        return ['@@ -1 +1 @@\n-Be long.\n+Be brief.', ''][index];
    }
    prompt_history_restore(id, field, index) {
        this.write([id], { instructions: `restored ${index}` });
        return false;
    }
}

defineAIModels(PromptModel);

async function openHistory(resId) {
    await mountWebClient();
    await getService(ActionPlugin).doAction({
        type: 'ir.actions.client',
        tag: 'muk_ai.prompt_history_dialog',
        params: {
            res_model: 'muk_ai.test_prompt',
            res_id: resId,
            field_name: 'instructions',
            field_label: 'Instructions',
        },
    });
    await waitFor('.mk_prompt_history');
}

test('the history lists the revisions, shows the diff of the one picked and restores it', async () => {
    await openHistory(1);
    expect('.modal-title').toHaveText('Instructions: History');
    expect(queryAllTexts('.mk_prompt_history_list .text-muted')).toEqual([
        'Mitchell Admin',
        'Marc Demo',
    ]);
    expect('.mk_prompt_history_list .active').toHaveText(/Mitchell Admin/);
    expect('.mk_prompt_history pre.language-diff code').toHaveText(
        '@@ -1 +1 @@\n-Be long.\n+Be brief.',
    );
    await contains('.mk_prompt_history_list button:contains(Marc Demo)').click();
    expect('.mk_prompt_history .mk_markdown').toHaveText('No differences.');
    await contains('.modal-footer .btn-primary').click();
    expect('.modal').toHaveCount(0);
    expect(
        MockServer.env['muk_ai.test_prompt'].read([1], ['instructions'])[0]
            .instructions,
    ).toBe('restored 1');
});

test('a field without history says so and has nothing to restore', async () => {
    await openHistory(2);
    expect('.mk_prompt_history_list').toHaveText('No history yet.');
    expect('.mk_prompt_history .mk_markdown').toHaveText('No differences.');
    expect('.modal-footer .btn-primary').toHaveProperty('disabled', true);
});
