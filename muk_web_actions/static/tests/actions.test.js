import { expect, test } from "@odoo/hoot";
import { session } from "@web/session";

import "@muk_web_actions/search/action_menus/action_menus";

import { ActionMenus } from "@web/search/action_menus/action_menus";

test.tags("muk_web_actions");
test("executeAction batches active ids and blocks UI", async () => {
    const doActionCalls = [];
    const self = {
        props: {
            getActiveIds: () => [1, 2, 3, 4, 5],
            isDomainSelected: false,
            resModel: "product",
            domain: [["id", ">", 0]],
            context: { test: true },
            onActionExecuted: () => expect.step("action.executed"),
        },
        uiService: {
            block: () => expect.step("ui.block"),
            unblock: () => expect.step("ui.unblock"),
        },
        blockProgressService: {
            block: ({ totalSteps }) => expect.step(`progress.block:${totalSteps}`),
            unblock: () => expect.step("progress.unblock"),
        },
        actionService: {
            doAction: async (actionId, options) => {
                doActionCalls.push({ actionId, options });
                options?.onClose?.();
            },
        },
    };
    await ActionMenus.prototype.executeAction.call(self, {
        id: 99,
        execute_in_batch: true,
        execution_batch_size: 2,
    });
    expect(doActionCalls).toHaveLength(3);
    expect(doActionCalls[0].options.additionalContext.active_ids).toEqual([1, 2]);
    expect(doActionCalls[1].options.additionalContext.active_ids).toEqual([3, 4]);
    expect(doActionCalls[2].options.additionalContext.active_ids).toEqual([5]);
    expect.verifySteps([
        "ui.block",
        "progress.block:3",
        "action.executed",
        "action.executed",
        "action.executed",
        "ui.unblock",
        "progress.unblock",
    ]);
});

test.tags("muk_web_actions");
test("executeAction uses domain selection search", async () => {
    const realActiveIdsLimit = session.active_ids_limit;
    session.active_ids_limit = 80;
    try {
        const doActionCalls = [];
        const ormCalls = [];
        const self = {
            props: {
                getActiveIds: () => [],
                isDomainSelected: true,
                resModel: "product",
                domain: [["id", ">", 0]],
                context: {},
                onActionExecuted: () => {},
            },
            orm: {
                search: async (model, domain, options) => {
                    ormCalls.push({ model, domain, options });
                    return [10, 11, 12];
                },
            },
            uiService: { block: () => {}, unblock: () => {} },
            blockProgressService: { block: () => {}, unblock: () => {} },
            actionService: {
                doAction: async (actionId, options) => {
                    doActionCalls.push({ actionId, options });
                },
            },
        };
        await ActionMenus.prototype.executeAction.call(self, {
            id: 42,
            execute_in_batch: true,
            execution_batch_size: 2,
        });
        expect(ormCalls).toHaveLength(1);
        expect(doActionCalls).toHaveLength(2);
        expect(doActionCalls[0].options.additionalContext.active_ids).toEqual([10, 11]);
        expect(doActionCalls[1].options.additionalContext.active_ids).toEqual([12]);
    } finally {
        session.active_ids_limit = realActiveIdsLimit;
    }
});
