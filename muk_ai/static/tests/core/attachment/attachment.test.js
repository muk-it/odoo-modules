import { describe, expect, test } from '@odoo/hoot';

import { toFileModel, toFileModels } from '@muk_ai/core/attachment/attachment';

describe.current.tags('muk_ai');

test('toFileModel maps descriptor fields and sets type=binary', () => {
    const file = toFileModel({
        id: 1,
        filename: 'a.png',
        mimetype: 'image/png',
        size: 100,
    });
    expect(file.id).toBe(1);
    expect(file.name).toBe('a.png');
    expect(file.mimetype).toBe('image/png');
    expect(file.size).toBe(100);
    expect(file.type).toBe('binary');
});

test('toFileModel returns the same instance when given an existing AIAttachment', () => {
    const first = toFileModel({
        id: 1,
        filename: 'a.png',
        mimetype: 'image/png',
        size: 1,
    });
    const second = toFileModel(first);
    expect(second).toBe(first);
});

test('toFileModels handles missing / empty input gracefully', () => {
    expect(toFileModels(undefined)).toEqual([]);
    expect(toFileModels(null)).toEqual([]);
    expect(toFileModels([])).toEqual([]);
});

test('toFileModels maps every descriptor', () => {
    const models = toFileModels([
        { id: 1, filename: 'a.png', mimetype: 'image/png', size: 1 },
        { id: 2, filename: 'b.pdf', mimetype: 'application/pdf', size: 2 },
    ]);
    expect(models.length).toBe(2);
    expect(models[0].name).toBe('a.png');
    expect(models[1].mimetype).toBe('application/pdf');
});

test('isText recognizes csv and markdown in addition to FileModelMixin defaults', () => {
    const csv = toFileModel({
        id: 1,
        filename: 'x.csv',
        mimetype: 'text/csv',
        size: 1,
    });
    const md = toFileModel({
        id: 2,
        filename: 'x.md',
        mimetype: 'text/markdown',
        size: 1,
    });
    const png = toFileModel({
        id: 3,
        filename: 'x.png',
        mimetype: 'image/png',
        size: 1,
    });
    expect(csv.isText).toBe(true);
    expect(md.isText).toBe(true);
    expect(png.isText).toBe(false);
});

test('isText still honors FileModelMixin defaults (text/plain)', () => {
    const txt = toFileModel({
        id: 1,
        filename: 'x.txt',
        mimetype: 'text/plain',
        size: 1,
    });
    expect(txt.isText).toBe(true);
});
