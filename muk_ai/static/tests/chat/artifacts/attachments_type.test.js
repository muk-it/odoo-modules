import { describe, expect, test } from '@odoo/hoot';

import { collectAttachments } from '@muk_ai/chat/artifacts/types/attachments_type';

describe.current.tags('muk_ai');

function toolResult(result) {
    return { events: [{ kind: 'tool_result', name: 'export_records', result }] };
}

describe('attachments artifacts tab', () => {
    test('a stored export becomes an attachment card', () => {
        const items = collectAttachments(
            toolResult(
                JSON.stringify({
                    filename: 'res_partner.csv',
                    mimetype: 'text/csv',
                    row_count: 5,
                    attachment_id: 42,
                    url: '/web/content/42?download=1',
                }),
            ),
        );
        expect(items).toEqual([
            { id: 42, filename: 'res_partner.csv', mimetype: 'text/csv' },
        ]);
    });

    test('a file nested in a tool_load wrapper is still found', () => {
        const items = collectAttachments(
            toolResult({
                loaded: { export_records: {} },
                call: {
                    name: 'export_records',
                    ok: true,
                    output: JSON.stringify({
                        filename: 'res_partner.xlsx',
                        mimetype: 'application/vnd.ms-excel',
                        attachment_id: 7,
                    }),
                },
            }),
        );
        expect(items).toEqual([
            {
                id: 7,
                filename: 'res_partner.xlsx',
                mimetype: 'application/vnd.ms-excel',
            },
        ]);
    });

    test('the same file reported twice is listed once', () => {
        const payload = JSON.stringify({
            filename: 'a.csv',
            mimetype: 'text/csv',
            attachment_id: 9,
        });
        const items = collectAttachments({
            events: [
                { kind: 'tool_result', name: 'export_records', result: payload },
                {
                    kind: 'tool_result',
                    name: 'tool_load',
                    result: { call: { output: payload } },
                },
            ],
        });
        expect(items).toHaveLength(1);
    });

    test('a tool result carrying no file adds nothing', () => {
        expect(collectAttachments(toolResult('{"records": [], "length": 0}'))).toEqual(
            [],
        );
        expect(collectAttachments(toolResult('plain text'))).toEqual([]);
        expect(collectAttachments(toolResult(null))).toEqual([]);
    });

    test('uploads and inline images still come through', () => {
        const items = collectAttachments({
            pendingAttachments: [
                { id: 1, filename: 'up.pdf', mimetype: 'application/pdf' },
            ],
            events: [
                { kind: 'text', content: '![chart](/web/image/5)' },
                {
                    kind: 'tool_result',
                    name: 'export_records',
                    result: '{"attachment_id": 8, "filename": "e.csv", "mimetype": "text/csv"}',
                },
            ],
        });
        expect(items.map((i) => i.id)).toEqual([1, 5, 8]);
    });
});
