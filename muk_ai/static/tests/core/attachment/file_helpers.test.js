import { describe, expect, test } from '@odoo/hoot';

import { fileToBase64 } from '@muk_ai/core/attachment/file_helpers';

describe.current.tags('muk_ai');

test('fileToBase64 preserves filename + mimetype + base64 payload', async () => {
    const file = new File(['hello'], 'greeting.txt', { type: 'text/plain' });
    const result = await fileToBase64(file);
    expect(result.filename).toBe('greeting.txt');
    expect(result.mimetype).toBe('text/plain');
    expect(result.data_b64).toBe(btoa('hello'));
});

test('fileToBase64 falls back to extension mimetype when type is empty', async () => {
    const file = new File(['x'], 'notes.md', { type: '' });
    const result = await fileToBase64(file);
    expect(result.mimetype).toBe('text/markdown');
});

test('fileToBase64 guesses csv + txt + markdown variants', async () => {
    const csv = await fileToBase64(new File(['x'], 'a.csv', { type: '' }));
    expect(csv.mimetype).toBe('text/csv');
    const txt = await fileToBase64(new File(['x'], 'a.txt', { type: '' }));
    expect(txt.mimetype).toBe('text/plain');
    const md = await fileToBase64(new File(['x'], 'a.MARKDOWN', { type: '' }));
    expect(md.mimetype).toBe('text/markdown');
});

test('fileToBase64 returns empty mimetype for unknown extension', async () => {
    const file = new File(['x'], 'weird.xyz', { type: '' });
    const result = await fileToBase64(file);
    expect(result.mimetype).toBe('');
});

test('fileToBase64 returns empty mimetype when filename has no extension', async () => {
    const file = new File(['x'], 'README', { type: '' });
    const result = await fileToBase64(file);
    expect(result.mimetype).toBe('');
});

test('fileToBase64 rejects with the reader error when the read fails', async () => {
    const OriginalFileReader = window.FileReader;
    class FailingFileReader {
        readAsDataURL() {
            this.error = new Error('the file went away mid-read');
            Promise.resolve().then(() => this.onerror());
        }
    }
    window.FileReader = FailingFileReader;
    let caught = null;
    try {
        await fileToBase64(new File(['x'], 'gone.txt', { type: 'text/plain' }));
    } catch (error) {
        caught = error;
    } finally {
        window.FileReader = OriginalFileReader;
    }
    expect(caught).not.toBe(null);
    expect(caught.message).toBe('the file went away mid-read');
});
