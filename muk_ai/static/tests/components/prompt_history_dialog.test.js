import { describe, expect, test } from '@odoo/hoot';
import { queryAllTexts } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
import {
    makeDialogMockEnv,
    mockService,
    mountWithCleanup,
    onRpc,
    patchTranslations,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { registry } from '@web/core/registry';

import { PromptHistoryDialog } from '@muk_ai/components/prompt_history_dialog/prompt_history_dialog';

describe.current.tags('muk_ai');
defineMailModels();

const DIFF = [
    '--- before',
    '+++ after',
    '@@ -1,3 +1,3 @@',
    ' keep this line',
    '-drop this line',
    '+add this line',
].join('\n');

function mockHistory(entries, diffByIndex = {}) {
    const asked = [];
    onRpc('muk_ai.agent', 'read', () => [
        { id: 3, prompt_history_metadata: { system_prompt: entries } },
    ]);
    onRpc('muk_ai.agent', 'prompt_history_unified_diff', ({ args }) => {
        asked.push(args);
        return diffByIndex[args[2]] ?? DIFF;
    });
    return asked;
}

async function mountDialog(overrides = {}) {
    const env = await makeDialogMockEnv();
    const dialog = await mountWithCleanup(PromptHistoryDialog, {
        env,
        props: {
            close: () => {},
            resModel: 'muk_ai.agent',
            resId: 3,
            fieldName: 'system_prompt',
            fieldLabel: 'System Prompt',
            ...overrides,
        },
    });
    await animationFrame();
    return dialog;
}

test('the dialog loads the revisions and diffs the newest one', async () => {
    const asked = mockHistory([
        { create_date: '2026-07-01 08:00:00', create_user_name: 'Ann' },
        { create_date: '2026-06-01 08:00:00', create_user_name: 'Bob' },
    ]);
    const dialog = await mountDialog();
    expect(dialog.state.entries).toHaveLength(2);
    expect(dialog.state.entries[1].index).toBe(1);
    expect(dialog.state.selectedIndex).toBe(0);
    expect(asked).toEqual([[3, 'system_prompt', 0]]);
    expect(dialog.state.diffLines.map((l) => l.kind)).toEqual([
        'meta',
        'meta',
        'hunk',
        'context',
        'removed',
        'added',
    ]);
    expect(dialog.state.loading).toBe(false);
});

test('the rendered diff tags added, removed and context lines', async () => {
    mockHistory([{ create_date: '2026-07-01 08:00:00', create_user_name: 'Ann' }]);
    await mountDialog();
    expect(queryAllTexts('.mk_prompt_history_added')).toEqual(['+add this line']);
    expect(queryAllTexts('.mk_prompt_history_removed')).toEqual(['-drop this line']);
    expect(queryAllTexts('.mk_prompt_history_hunk')).toEqual(['@@ -1,3 +1,3 @@']);
});

test('a field with no history selects nothing and shows no diff', async () => {
    const asked = mockHistory([]);
    const dialog = await mountDialog();
    expect(dialog.state.entries).toEqual([]);
    expect(dialog.state.selectedIndex).toBe(null);
    expect(dialog.state.diffLines).toEqual([]);
    expect(asked).toEqual([]);
});

test('a record without history metadata at all is handled', async () => {
    onRpc('muk_ai.agent', 'read', () => [{ id: 3 }]);
    const dialog = await mountDialog();
    expect(dialog.state.entries).toEqual([]);
    expect(dialog.state.selectedIndex).toBe(null);
});

test('an identical revision renders a single no-difference row', async () => {
    mockHistory([{ create_date: '2026-07-01 08:00:00', create_user_name: 'Ann' }], {
        0: '   \n',
    });
    const dialog = await mountDialog();
    expect(dialog.state.diffLines).toHaveLength(1);
    expect(dialog.state.diffLines[0].kind).toBe('empty');
});

test('selecting an older revision fetches its own diff', async () => {
    const asked = mockHistory(
        [
            { create_date: '2026-07-01 08:00:00', create_user_name: 'Ann' },
            { create_date: '2026-06-01 08:00:00', create_user_name: 'Bob' },
        ],
        { 1: '@@ -1 +1 @@\n-old\n+new' },
    );
    const dialog = await mountDialog();
    await dialog.selectRevision(1);
    expect(asked.at(-1)).toEqual([3, 'system_prompt', 1]);
    expect(dialog.state.selectedIndex).toBe(1);
    expect(dialog.state.diffLines.map((l) => l.kind)).toEqual([
        'hunk',
        'removed',
        'added',
    ]);
});

test('restoring a revision dispatches the returned action and closes', async () => {
    mockHistory([{ create_date: '2026-07-01 08:00:00', create_user_name: 'Ann' }]);
    let restoreArgs = null;
    onRpc('muk_ai.agent', 'prompt_history_restore', ({ args }) => {
        restoreArgs = args;
        return { type: 'ir.actions.act_window', res_model: 'muk_ai.agent' };
    });
    const dispatched = [];
    mockService('action', {
        doAction: (action) => dispatched.push(action),
        loadAction: () => ({}),
    });
    let closed = 0;
    const dialog = await mountDialog({
        close: () => {
            closed++;
        },
    });
    await dialog.onRestore();
    expect(restoreArgs).toEqual([3, 'system_prompt', 0]);
    expect(dispatched).toHaveLength(1);
    expect(closed).toBe(1);
});

test('restoring closes without dispatching when the server returns nothing', async () => {
    mockHistory([{ create_date: '2026-07-01 08:00:00', create_user_name: 'Ann' }]);
    onRpc('muk_ai.agent', 'prompt_history_restore', () => false);
    const dispatched = [];
    mockService('action', {
        doAction: (action) => dispatched.push(action),
        loadAction: () => ({}),
    });
    let closed = 0;
    const dialog = await mountDialog({
        close: () => {
            closed++;
        },
    });
    await dialog.onRestore();
    expect(dispatched).toEqual([]);
    expect(closed).toBe(1);
});

test('restore is a noop while no revision is selected', async () => {
    mockHistory([]);
    let restored = 0;
    onRpc('muk_ai.agent', 'prompt_history_restore', () => {
        restored++;
        return false;
    });
    let closed = 0;
    const dialog = await mountDialog({
        close: () => {
            closed++;
        },
    });
    await dialog.onRestore();
    expect(restored).toBe(0);
    expect(closed).toBe(0);
});

test('the history action opens the dialog and closes the action window', async () => {
    patchTranslations();
    const opened = [];
    const env = {
        services: {
            dialog: {
                add: (component, props) => {
                    opened.push({ component, props });
                },
            },
        },
    };
    const handler = registry.category('actions').get('muk_ai.prompt_history_dialog');
    const result = handler(env, {
        params: { res_model: 'muk_ai.agent', res_id: 3, field_name: 'system_prompt' },
    });
    expect(result).toEqual({ type: 'ir.actions.act_window_close' });
    expect(opened).toHaveLength(1);
    expect(opened[0].component).toBe(PromptHistoryDialog);
    expect(opened[0].props.resId).toBe(3);
    expect(opened[0].props.fieldName).toBe('system_prompt');
    expect(String(opened[0].props.fieldLabel)).toBe('Field');
});
