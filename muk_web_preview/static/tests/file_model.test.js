import { expect, test } from '@odoo/hoot';

import { session } from '@web/session';
import { patchWithCleanup } from '@web/../tests/web_test_helpers';

import { FileModel } from '@web/core/file_viewer/file_model';

import '@muk_web_preview/core/file_viewer/file_model';

/**
 * Build a file model carrying the given mimetype and name.
 * @param {string} mimetype the file mimetype
 * @param {string} name the file name
 * @param {number} [id] the attachment id
 * @returns {object} the file model instance
 */
function makeFile(mimetype, name, id = 1) {
    const file = Object.create(FileModel.prototype);
    file.mimetype = mimetype;
    file.name = name;
    file.id = id;
    file.uploading = false;
    Object.defineProperty(file, 'urlQueryParams', { value: {} });
    return file;
}

test.tags('muk_web_preview');
test('isMail returns true for message/rfc822', () => {
    const file = Object.create(FileModel.prototype);
    file.mimetype = 'message/rfc822';
    file.name = 'test.eml';
    expect(file.isMail).toBe(true);
});

test.tags('muk_web_preview');
test('isMail returns false for text/plain', () => {
    const file = Object.create(FileModel.prototype);
    file.mimetype = 'text/plain';
    file.name = 'test.txt';
    expect(file.isMail).toBe(false);
});

test.tags('muk_web_preview');
test('isCSV returns true for text/csv', () => {
    const file = Object.create(FileModel.prototype);
    file.mimetype = 'text/csv';
    file.name = 'data.csv';
    expect(file.isCSV).toBe(true);
});

test.tags('muk_web_preview');
test('isCSV returns true for .tsv extension', () => {
    const file = Object.create(FileModel.prototype);
    file.mimetype = 'text/tab-separated-values';
    file.name = 'data.tsv';
    expect(file.isCSV).toBe(true);
});

test.tags('muk_web_preview');
test('isCSV returns true by extension fallback', () => {
    const file = Object.create(FileModel.prototype);
    file.mimetype = 'application/octet-stream';
    file.name = 'export.csv';
    expect(file.isCSV).toBe(true);
});

test.tags('muk_web_preview');
test('isCSV returns false for unrelated mimetype', () => {
    const file = Object.create(FileModel.prototype);
    file.mimetype = 'text/plain';
    file.name = 'notes.txt';
    expect(file.isCSV).toBe(false);
});

test.tags('muk_web_preview');
test('isText returns true for text/markdown', () => {
    const file = Object.create(FileModel.prototype);
    file.mimetype = 'text/markdown';
    file.name = 'readme.md';
    expect(file.isText).toBe(true);
});

test.tags('muk_web_preview');
test('isText returns true for text/x-python', () => {
    const file = Object.create(FileModel.prototype);
    file.mimetype = 'text/x-python';
    file.name = 'script.py';
    expect(file.isText).toBe(true);
});

test.tags('muk_web_preview');
test('isText returns true for application/xml', () => {
    const file = Object.create(FileModel.prototype);
    file.mimetype = 'application/xml';
    file.name = 'config.xml';
    expect(file.isText).toBe(true);
});

test.tags('muk_web_preview');
test('isText returns true for application/sql', () => {
    const file = Object.create(FileModel.prototype);
    file.mimetype = 'application/sql';
    file.name = 'query.sql';
    expect(file.isText).toBe(true);
});

test.tags('muk_web_preview');
test('defaultSource returns mail URL for eml files', () => {
    const file = Object.create(FileModel.prototype);
    file.mimetype = 'message/rfc822';
    file.name = 'test.eml';
    file.id = 42;
    Object.defineProperty(file, 'urlQueryParams', { value: {} });
    const src = file.defaultSource;
    expect(src).toInclude('/muk_web_preview/preview/mail/42');
});

test.tags('muk_web_preview');
test('defaultSource returns csv URL for csv files', () => {
    const file = Object.create(FileModel.prototype);
    file.mimetype = 'text/csv';
    file.name = 'data.csv';
    file.id = 99;
    Object.defineProperty(file, 'urlQueryParams', { value: {} });
    const src = file.defaultSource;
    expect(src).toInclude('/muk_web_preview/preview/csv/99');
});

test.tags('muk_web_preview');
test('isOffice stays false while the office preview is disabled', () => {
    patchWithCleanup(session, { preview_office_enabled: false });
    const file = makeFile(
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'report.docx',
    );
    expect(file.isOffice).toBe(false);
});

test.tags('muk_web_preview');
test('isOffice recognises office mimetypes once enabled', () => {
    patchWithCleanup(session, { preview_office_enabled: true });
    for (const mimetype of [
        'application/msword',
        'application/vnd.ms-excel',
        'application/vnd.ms-powerpoint',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    ]) {
        expect(makeFile(mimetype, 'file.bin').isOffice).toBe(true);
    }
});

test.tags('muk_web_preview');
test('isOffice falls back to the office file extensions', () => {
    patchWithCleanup(session, { preview_office_enabled: true });
    for (const name of ['a.doc', 'a.docx', 'b.xls', 'b.xlsx', 'c.ppt', 'c.pptx']) {
        expect(makeFile('application/octet-stream', name).isOffice).toBe(true);
    }
    expect(makeFile('application/octet-stream', 'notes.odt').isOffice).toBe(false);
});

test.tags('muk_web_preview');
test('isViewable covers the added preview types', () => {
    patchWithCleanup(session, { preview_office_enabled: true });
    expect(makeFile('message/rfc822', 'mail.eml').isViewable).toBe(true);
    expect(makeFile('text/csv', 'data.csv').isViewable).toBe(true);
    expect(makeFile('text/markdown', 'readme.md').isViewable).toBe(true);
    expect(makeFile('application/vnd.ms-excel', 'sheet.xls').isViewable).toBe(true);
});

test.tags('muk_web_preview');
test('an uploading file of an added type is not viewable yet', () => {
    const file = makeFile('message/rfc822', 'mail.eml');
    file.uploading = true;
    expect(file.isViewable).toBe(false);
});

test.tags('muk_web_preview');
test('a plain binary stays outside the added preview types', () => {
    patchWithCleanup(session, { preview_office_enabled: true });
    const file = makeFile('application/octet-stream', 'archive.zip');
    expect(file.isMail).toBe(false);
    expect(file.isCSV).toBe(false);
    expect(file.isOffice).toBe(false);
    expect(file.isText).toBe(false);
    expect(file.isViewable).toBe(false);
});

test.tags('muk_web_preview');
test('defaultSource keeps the core source for other types', () => {
    const file = makeFile('text/markdown', 'readme.md', 7);
    expect(file.defaultSource).not.toInclude('/muk_web_preview/preview/');
});
