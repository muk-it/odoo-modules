import { advanceTime, expect, test } from '@odoo/hoot';
import { onRpc } from '@web/../tests/web_test_helpers';

import { clientTools } from '@muk_ai/core/client_tools/client_tools';
import {
    defineAIModels,
    emitEvent,
    openSession,
    snapshot,
} from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();

const action = (callId, args = '{"x": 1}', name = 'probe') => ({
    kind: 'client_action',
    call_id: callId,
    name,
    arguments: args,
});

function trackAnswers() {
    onRpc('muk_ai.session', 'submit_client_result', ({ args }) => {
        expect.step(`submit ${args[1]} ${JSON.stringify(args[2])}`);
        return snapshot();
    });
    onRpc('muk_ai.session', 'reject_client_action', ({ args, kwargs }) => {
        expect.step(`reject ${args[1]} ${kwargs.reason}`);
        return snapshot();
    });
}

test('a client action runs its tool once and posts the outcome back', async () => {
    trackAnswers();
    clientTools.add('probe', { execute: async (args) => ({ seen: args.x }) });
    clientTools.add('broken', {
        execute: async () => {
            throw new Error('no view');
        },
    });
    await openSession(1);
    await emitEvent(1, 'log', action('c1'));
    await emitEvent(1, 'log', action('c1'));
    await emitEvent(1, 'log', action('c2', '{"x": '));
    await emitEvent(1, 'log', action('c3', '{}', 'broken'));
    await emitEvent(1, 'log', action('c4', '{}', 'not_registered'));
    await emitEvent(1, 'log', action('c8', ''));
    await emitEvent(1, 'log', action('c9', '"text"'));
    await expect.waitForSteps([
        'submit c1 {"seen":1}',
        'reject c2 client received corrupt or truncated tool arguments',
        'reject c3 no view',
        'submit c8 {}',
        'reject c9 client received corrupt or truncated tool arguments',
    ]);
});

test('a tool asking for a delay runs after it', async () => {
    trackAnswers();
    clientTools.add('slow', { execute: async () => 'late', defer: () => 500 });
    await openSession(1);
    await emitEvent(1, 'log', action('c5', '{}', 'slow'));
    expect.verifySteps([]);
    await advanceTime(500);
    await expect.waitForSteps(['submit c5 "late"']);
});

test('only a tab steering the chat answers, never one reading it or not showing it', async () => {
    trackAnswers();
    clientTools.add('probe', { execute: async () => 'ran' });
    onRpc('muk_ai.session', 'get_snapshot', ({ args }) =>
        snapshot({ id: args[0], can_write: args[0] !== 2 }),
    );
    const shown = await openSession(1);
    await openSession(2);
    shown.chat.release(1);
    await emitEvent(1, 'log', action('c6'));
    await emitEvent(2, 'log', action('c7'));
    expect.verifySteps([]);
});
