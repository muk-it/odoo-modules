// @odoo-module

import { makeClientToolListener } from '@muk_ai/chat/client/executor';
import {
    registerOpenSession,
    unregisterOpenSession,
} from '@muk_ai/chat/session/open_sessions';

/**
 * Let every pending promise and timer of the moment run.
 */
async function flush() {
    for (let round = 0; round < 10; round++) {
        await new Promise((resolve) => setTimeout(resolve, 0));
    }
}

/**
 * Build the bus event of a client action the session waits for.
 * @param {string} callId the call
 * @returns {object} the `muk_ai.event` payload
 */
function action(callId) {
    return {
        type: 'log',
        session_id: 7,
        payload: {
            kind: 'client_action',
            call_id: callId,
            name: 'probe',
            arguments: '{}',
        },
    };
}

QUnit.module('client_tools', {
    beforeEach() {
        registerOpenSession(7);
    },
    afterEach() {
        unregisterOpenSession(7);
    },
});

QUnit.test(
    'the results of one batch reach the session one after the other',
    async (assert) => {
        let release;
        const orm = {
            async call(model, method, [, callId]) {
                assert.step(`start ${callId}`);
                if (callId === 'b1') {
                    await new Promise((resolve) => (release = resolve));
                }
                assert.step(`end ${callId}`);
            },
        };
        const onEvent = makeClientToolListener({
            orm,
            contains: () => true,
            execute: async () => 'ok',
        });
        onEvent(action('b1'));
        onEvent(action('b2'));
        await flush();
        assert.verifySteps(['start b1']);
        release();
        await flush();
        assert.verifySteps(['end b1', 'start b2', 'end b2']);
    },
);
