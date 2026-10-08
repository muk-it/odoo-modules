import { expect, mockDate, test } from '@odoo/hoot';

import {
    fileToBase64,
    toFileModel,
    transferFiles,
} from '@muk_ai/core/attachment/attachment';
import {
    formatCost,
    formatError,
    formatRelativeTime,
    formatTimestamp,
    statusInfo,
} from '@muk_ai/core/utils/utils';
import { agentSuggestions } from '@muk_ai/chat/conversation/conversation';
import { defineAIModels, getChat } from '@muk_ai/../tests/muk_ai_test_helpers';

defineAIModels();

test('every session state has a label, an icon and a colour, unknown ones read as new', () => {
    expect(statusInfo('running')).toMatchObject({
        icon: 'progress_activity',
        cls: 'mk_state_running',
        spin: true,
    });
    expect(statusInfo('waiting_schedule').cls).toBe('mk_state_waiting');
    expect(statusInfo('archived')).toMatchObject({
        label: 'archived',
        cls: 'mk_state_new',
    });
});

test('costs keep a precision matching their magnitude', () => {
    expect([0, 0.00123, 0.4567, 12.345].map(formatCost)).toEqual([
        '0',
        '0.0012',
        '0.457',
        '12.35',
    ]);
});

test('the time left until a timestamp shows in its two largest units', async () => {
    mockDate('2026-01-01 10:00:00', 0);
    await getChat();
    expect(
        [
            '2026-01-01 10:00:30',
            '2026-01-01 10:05:03',
            '2026-01-01T12:30:00',
            '2026-01-03 13:00:00',
            '2026-01-01 09:00:00',
            'not a date',
        ].map(formatRelativeTime),
    ).toEqual(['30s', '5m 3s', '2h 30m', '2d 3h', '', '']);
    expect(formatTimestamp('2026-01-01 10:00:00')).toInclude('10:00');
    expect(formatTimestamp('')).toBe('');
});

test('an error message is read from an RPC error, an exception or a value', () => {
    expect(
        [
            { data: { message: 'rpc' }, message: 'outer' },
            new Error('plain'),
            'text',
        ].map(formatError),
    ).toEqual(['rpc', 'plain', 'text']);
});

test('files read as base64 payloads with a mimetype guessed from their name', async () => {
    const payloads = await Promise.all([
        fileToBase64(new File(['# hi'], 'notes.md')),
        fileToBase64(new File(['a,b'], 'table.CSV')),
        fileToBase64(new File(['x'], 'shot', { type: 'image/png' })),
    ]);
    expect(payloads.map((payload) => [payload.filename, payload.mimetype])).toEqual([
        ['notes.md', 'text/markdown'],
        ['table.CSV', 'text/csv'],
        ['shot', 'image/png'],
    ]);
    expect(atob(payloads[0].data_b64)).toBe('# hi');
    const transfer = new DataTransfer();
    transfer.items.add(new File(['x'], 'a.txt'));
    transfer.items.add('just text', 'text/plain');
    expect(transferFiles(transfer).map((file) => file.name)).toEqual(['a.txt']);
});

test('an attachment opens in the file viewer with its route', () => {
    const image = toFileModel({ id: 5, filename: 'a.png', mimetype: 'image/png' });
    const text = toFileModel({ id: 6, filename: 'b.csv', mimetype: 'text/csv' });
    expect([image.isImage, image.urlRoute, text.isText, text.isViewable]).toEqual([
        true,
        '/web/image/5',
        true,
        true,
    ]);
});

test('an agent offers the suggestions that carry a prompt', () => {
    expect(
        agentSuggestions({
            suggestions: [
                { label: 'A', prompt: 'Do a' },
                { prompt: 'Do b' },
                { label: 'Empty', prompt: ' ' },
                null,
            ],
        }),
    ).toEqual([
        { label: 'A', prompt: 'Do a', preview: 'Do a' },
        { label: 'Do b', prompt: 'Do b', preview: 'Do b' },
    ]);
    expect(agentSuggestions(undefined)).toEqual([]);
});
