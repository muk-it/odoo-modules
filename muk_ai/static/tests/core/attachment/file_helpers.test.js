import { describe, expect, test } from '@odoo/hoot';

import { fileToBase64 } from '@muk_ai/core/attachment/file_helpers';

describe.current.tags('muk_ai');

test('files read as base64 payloads with the type the browser gives', async () => {
    expect(await fileToBase64(new File(['# hi'], 'notes.md'))).toEqual({
        filename: 'notes.md',
        mimetype: '',
        data_b64: btoa('# hi'),
    });
    expect(
        (await fileToBase64(new File(['x'], 'shot', { type: 'image/png' }))).mimetype,
    ).toBe('image/png');
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
