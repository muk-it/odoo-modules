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
    'the client actions of one batch run and report one after the other',
    async (assert) => {
        let release;
        let runs = 0;
        const orm = {
            async call(model, method, [, callId]) {
                assert.step(`post ${callId}`);
            },
        };
        const onEvent = makeClientToolListener({
            orm,
            contains: () => true,
            async execute() {
                const run = ++runs;
                assert.step(`run ${run}`);
                if (run === 1) {
                    await new Promise((resolve) => (release = resolve));
                }
                return 'ok';
            },
        });
        onEvent(action('b1'));
        onEvent(action('b2'));
        await flush();
        assert.verifySteps(['run 1']);
        release();
        await flush();
        assert.verifySteps(['post b1', 'run 2', 'post b2']);
    },
);
