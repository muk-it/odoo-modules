import { describe, expect, test } from '@odoo/hoot';

import { browser } from '@web/core/browser/browser';
import { session } from '@web/session';
import { parseXML } from '@web/core/utils/xml';
import { ListArchParser } from '@web/views/list/list_arch_parser';

import {
    removeColumnWidth,
    setColumnWidth,
} from '@muk_web_list_column/views/list/list_view_storage';

import '@muk_web_list_column/views/list/list_arch_parser';

describe.current.tags('muk_web_list_column');

const MODEL = 'muk.widthy';

const MODELS = {
    [MODEL]: {
        fields: {
            name: { type: 'char', string: 'Name' },
            sequence: { type: 'integer', string: 'Sequence' },
        },
    },
};

/**
 * Parse a list arch through the patched arch parser.
 * @param {string} arch the list arch to parse
 * @returns {object} the parsed arch info
 */
function parse(arch) {
    return new ListArchParser().parse(parseXML(arch), MODELS, MODEL);
}

/**
 * Return the parsed column carrying the given field name.
 * @param {object} archInfo the parsed arch info
 * @param {string} name the field name to look up
 * @returns {object} the matching column descriptor
 */
function columnFor(archInfo, name) {
    return archInfo.columns.find((col) => col.name === name);
}

test('a stored width is applied to a labelled column', async () => {
    const realDb = session.db;
    const realUid = session.uid;
    try {
        session.db = 'test_db';
        session.uid = 99;
        setColumnWidth(MODEL, 'name', '333px');
        const archInfo = parse('<list><field name="name"/></list>');
        expect(columnFor(archInfo, 'name').attrs.width).toBe('333px');
    } finally {
        session.db = realDb;
        session.uid = realUid;
        browser.localStorage.clear();
    }
});

test('an arch width is overridden by the stored one', async () => {
    const realDb = session.db;
    const realUid = session.uid;
    try {
        session.db = 'test_db';
        session.uid = 99;
        setColumnWidth(MODEL, 'name', '120px');
        const archInfo = parse('<list><field name="name" width="500px"/></list>');
        expect(columnFor(archInfo, 'name').attrs.width).toBe('120px');
    } finally {
        session.db = realDb;
        session.uid = realUid;
        browser.localStorage.clear();
    }
});

test('the arch width is kept when nothing was stored', async () => {
    const realDb = session.db;
    const realUid = session.uid;
    try {
        session.db = 'test_db';
        session.uid = 99;
        removeColumnWidth(MODEL, 'name');
        const archInfo = parse('<list><field name="name" width="500px"/></list>');
        expect(columnFor(archInfo, 'name').attrs.width).toBe('500px');
    } finally {
        session.db = realDb;
        session.uid = realUid;
        browser.localStorage.clear();
    }
});

test('widths stored for another model are not applied', async () => {
    const realDb = session.db;
    const realUid = session.uid;
    try {
        session.db = 'test_db';
        session.uid = 99;
        setColumnWidth('other.model', 'name', '777px');
        const archInfo = parse('<list><field name="name"/></list>');
        expect(columnFor(archInfo, 'name').attrs.width).toBe(undefined);
    } finally {
        session.db = realDb;
        session.uid = realUid;
        browser.localStorage.clear();
    }
});

test('an unlabelled column is left at its arch width', async () => {
    const realDb = session.db;
    const realUid = session.uid;
    try {
        session.db = 'test_db';
        session.uid = 99;
        setColumnWidth(MODEL, 'sequence', '400px');
        const archInfo = parse(
            '<list><field name="sequence" nolabel="1"/><field name="name"/></list>',
        );
        const unlabelled = columnFor(archInfo, 'sequence');
        expect(unlabelled.hasLabel).toBe(false);
        expect(unlabelled.attrs.width).toBe(undefined);
    } finally {
        session.db = realDb;
        session.uid = realUid;
        browser.localStorage.clear();
    }
});
