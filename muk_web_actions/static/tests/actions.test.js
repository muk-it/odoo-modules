import { expect, test } from '@odoo/hoot';
import { session } from '@web/session';

import { patchWithCleanup } from '@web/../tests/web_test_helpers';

import '@muk_web_actions/search/action_menus/action_menus';

import { ActionMenus } from '@web/search/action_menus/action_menus';

function makeActionMenus({
    activeIds = [1, 2, 3, 4, 5],
    isDomainSelected = false,
    domain = false,
    context = {},
    searchResult = [],
    onDoAction = async () => {},
} = {}) {
    patchWithCleanup(session, { test_mode: true });
    const doActionCalls = [];
    const ormCalls = [];
    const self = {
        props: {
            getActiveIds: () => activeIds,
            isDomainSelected,
            resModel: 'product',
            domain,
            context,
            onActionExecuted: () => expect.step('action.executed'),
        },
        orm: {
            search: async (model, searchDomain, options) => {
                ormCalls.push({ model, domain: searchDomain, options });
                return searchResult;
            },
        },
        uiService: {
            block: () => expect.step('ui.block'),
            unblock: () => expect.step('ui.unblock'),
        },
        blockProgressService: {
            block: ({ totalSteps }) => expect.step(`progress.block:${totalSteps}`),
            unblock: () => expect.step('progress.unblock'),
        },
        actionService: {
            doAction: async (actionId, options) => {
                doActionCalls.push({ actionId, options });
                return onDoAction(actionId, options);
            },
        },
    };
    return { self, doActionCalls, ormCalls };
}

function run(self, action) {
    return ActionMenus.prototype.executeAction.call(self, action);
}

test.tags('muk_web_actions');
test('executeAction batches active ids and blocks the ui', async () => {
    const { self, doActionCalls } = makeActionMenus({
        domain: [['id', '>', 0]],
        context: { test: true },
        onDoAction: (actionId, options) => options?.onClose?.(),
    });
    await run(self, {
        id: 99,
        execute_in_batch: true,
        execution_batch_size: 2,
    });
    expect(doActionCalls).toHaveLength(3);
    expect(doActionCalls[0].options.additionalContext.active_ids).toEqual([1, 2]);
    expect(doActionCalls[1].options.additionalContext.active_ids).toEqual([3, 4]);
    expect(doActionCalls[2].options.additionalContext.active_ids).toEqual([5]);
    expect(doActionCalls.every(({ actionId }) => actionId === 99)).toBe(true);
    expect.verifySteps([
        'ui.block',
        'progress.block:3',
        'action.executed',
        'action.executed',
        'action.executed',
        'ui.unblock',
        'progress.unblock',
    ]);
});

test.tags('muk_web_actions');
test('executeAction passes the leading id and the caller context along', async () => {
    const { self, doActionCalls } = makeActionMenus({
        activeIds: [7, 8, 9],
        domain: [['id', '>', 0]],
        context: { default_kind: 'x' },
    });
    await run(self, {
        id: 5,
        execute_in_batch: true,
        execution_batch_size: 2,
    });
    const [first, second] = doActionCalls.map(
        ({ options }) => options.additionalContext,
    );
    expect(first.active_id).toBe(7);
    expect(first.active_ids).toEqual([7, 8]);
    expect(first.active_model).toBe('product');
    expect(first.active_domain).toEqual([['id', '>', 0]]);
    expect(first.default_kind).toBe('x');
    expect(second.active_id).toBe(9);
    expect.verifySteps([
        'ui.block',
        'progress.block:2',
        'ui.unblock',
        'progress.unblock',
    ]);
});

test.tags('muk_web_actions');
test('executeAction omits the active domain when there is none', async () => {
    const { self, doActionCalls } = makeActionMenus({ activeIds: [1] });
    await run(self, { id: 5, execute_in_batch: true, execution_batch_size: 2 });
    expect(doActionCalls).toHaveLength(1);
    expect('active_domain' in doActionCalls[0].options.additionalContext).toBe(false);
    expect.verifySteps([
        'ui.block',
        'progress.block:1',
        'ui.unblock',
        'progress.unblock',
    ]);
});

test.tags('muk_web_actions');
test('executeAction falls back to a batch size of one', async () => {
    const { self, doActionCalls } = makeActionMenus({ activeIds: [1, 2, 3] });
    await run(self, { id: 5, execute_in_batch: true, execution_batch_size: 0 });
    expect(doActionCalls).toHaveLength(3);
    expect(doActionCalls[0].options.additionalContext.active_ids).toEqual([1]);
    expect.verifySteps([
        'ui.block',
        'progress.block:3',
        'ui.unblock',
        'progress.unblock',
    ]);
});

test.tags('muk_web_actions');
test('executeAction leaves non batch actions to the core implementation', async () => {
    const { self, doActionCalls } = makeActionMenus({
        activeIds: [1, 2, 3, 4, 5],
        domain: [['id', '>', 0]],
    });
    await run(self, { id: 5, execute_in_batch: false });
    expect(doActionCalls).toHaveLength(1);
    expect(doActionCalls[0].options.additionalContext.active_ids).toEqual([
        1, 2, 3, 4, 5,
    ]);
    expect.verifySteps([]);
});

test.tags('muk_web_actions');
test('executeAction leaves actions without the flag to the core implementation', async () => {
    const { self, doActionCalls } = makeActionMenus({ activeIds: [1, 2] });
    await run(self, { id: 6 });
    expect(doActionCalls).toHaveLength(1);
    expect(doActionCalls[0].options.additionalContext.active_ids).toEqual([1, 2]);
    expect.verifySteps([]);
});

test.tags('muk_web_actions');
test('executeAction unblocks the ui when a batch action rejects', async () => {
    let calls = 0;
    const { self } = makeActionMenus({
        onDoAction: () => {
            calls++;
            if (calls === 2) {
                throw new Error('boom');
            }
        },
    });
    await expect(
        run(self, { id: 99, execute_in_batch: true, execution_batch_size: 2 }),
    ).rejects.toThrow('boom');
    expect.verifySteps([
        'ui.block',
        'progress.block:3',
        'ui.unblock',
        'progress.unblock',
    ]);
});

test.tags('muk_web_actions');
test('executeAction resolves the ids server side when a domain is selected', async () => {
    patchWithCleanup(session, { active_ids_limit: 80 });
    const { self, doActionCalls, ormCalls } = makeActionMenus({
        activeIds: [],
        isDomainSelected: true,
        domain: [['id', '>', 0]],
        context: { lang: 'en_US' },
        searchResult: [10, 11, 12],
    });
    await run(self, { id: 42, execute_in_batch: true, execution_batch_size: 2 });
    expect(ormCalls).toHaveLength(1);
    expect(ormCalls[0].model).toBe('product');
    expect(ormCalls[0].domain).toEqual([['id', '>', 0]]);
    expect(ormCalls[0].options.limit).toBe(80);
    expect(ormCalls[0].options.context).toEqual({ lang: 'en_US' });
    expect(doActionCalls).toHaveLength(2);
    expect(doActionCalls[0].options.additionalContext.active_ids).toEqual([10, 11]);
    expect(doActionCalls[1].options.additionalContext.active_ids).toEqual([12]);
    expect.verifySteps([
        'ui.block',
        'progress.block:2',
        'ui.unblock',
        'progress.unblock',
    ]);
});

test.tags('muk_web_actions');
test('executeAction does nothing when the selection is empty', async () => {
    const { self, doActionCalls } = makeActionMenus({ activeIds: [] });
    await run(self, { id: 5, execute_in_batch: true, execution_batch_size: 2 });
    expect(doActionCalls).toHaveLength(0);
    expect.verifySteps([
        'ui.block',
        'progress.block:0',
        'ui.unblock',
        'progress.unblock',
    ]);
});
