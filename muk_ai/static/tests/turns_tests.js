// @odoo-module

import { buildRenderedTurns } from '@muk_ai/chat/session/turns';

QUnit.module('turns');

QUnit.test('the images a tool returns join its turn beside its card', (assert) => {
    const [, turn] = buildRenderedTurns([
        { kind: 'user_message', content: 'Show me', event_id: 1 },
        { kind: 'tool_call', call_id: 'c1', name: 'render_preview', arguments: '{}' },
        { kind: 'tool_result', call_id: 'c1', result: '{"text": "Captured"}' },
        {
            kind: 'tool_images',
            call_id: 'c1',
            images: [
                { url: '/web/image/7', name: 'desktop.png' },
                { url: '/web/image/8', name: 'mobile.png' },
            ],
        },
    ]);
    assert.deepEqual(
        turn.blocks.map((block) => block.type),
        ['tool', 'images'],
    );
    assert.deepEqual(
        turn.blocks[1].images.map((image) => image.url),
        ['/web/image/7', '/web/image/8'],
    );
});
