import { expect, test } from '@odoo/hoot';

import { FileModel } from '@web/core/file_viewer/file_model';

import '@muk_web_preview/core/file_viewer/file_model';

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
