// @odoo-module

import { buildRenderedTurns, isToolBlockHidden } from '@muk_ai/chat/session/turns';

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

QUnit.test(
    'a tool card stays out while a question or an approval shows its call, or as bookkeeping',
    (assert) => {
        const turn = {
            blocks: [
                { type: 'ask', callId: 'c2' },
                { type: 'ask', callId: 'c7' },
            ],
        };
        const cases = [
            [{ name: 'other', callId: 'c1', result: '{}' }, null, false],
            [{ name: 'ask_user', callId: 'c2', result: null }, null, true],
            [{ name: 'other', callId: 'c3', result: null }, { call_id: 'c3' }, true],
            [{ name: 'other', callId: 'c4', result: null }, null, false],
            [
                { name: 'update_records', callId: 'c7', result: '{"ok": true}' },
                null,
                true,
            ],
            [
                { name: 'update_records', callId: 'c7', result: '{"error": "x"}' },
                null,
                false,
            ],
            [{ name: 'tool_load', callId: 'c10', result: '{}' }, null, true],
            [{ name: 'other', callId: 'c11', result: '{"skipped": true}' }, null, true],
        ];
        for (const [block, pending, hidden] of cases) {
            assert.strictEqual(
                isToolBlockHidden(block, turn, pending),
                hidden,
                block.callId,
            );
        }
    },
);

QUnit.test(
    'an image the answer draws inline is not listed again as a file',
    (assert) => {
        const [, turn] = buildRenderedTurns([
            { kind: 'user_message', content: 'Show', event_id: 1 },
            {
                kind: 'tool_call',
                call_id: 'c1',
                name: 'generate_image',
                arguments: '{}',
            },
            {
                kind: 'tool_result',
                call_id: 'c1',
                result: JSON.stringify({
                    files: [
                        {
                            attachment_id: 5,
                            filename: 'chart.png',
                            mimetype: 'image/png',
                        },
                        {
                            attachment_id: 6,
                            filename: 'data.csv',
                            mimetype: 'text/csv',
                        },
                    ],
                }),
            },
            { kind: 'text', content: '![chart](/web/image/5)', event_id: 2 },
        ]);
        assert.deepEqual(
            turn.attachments.map((file) => file.filename),
            ['data.csv'],
        );
    },
);
