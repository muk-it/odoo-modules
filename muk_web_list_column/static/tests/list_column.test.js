import { session } from '@web/session';
import { browser } from '@web/core/browser/browser';
import { expect, test } from '@odoo/hoot';

import {
    getColumnWidth,
    removeColumnWidth,
    setColumnWidth,
} from '@muk_web_list_column/views/list/list_view_storage';

import { ListRenderer } from '@web/views/list/list_renderer';

import '@muk_web_list_column/views/list/list_renderer';

test.tags('muk_web_list_column');
test('column width is stored and restored from localStorage', async () => {
    const realDb = session.db;
    const realUid = session.uid;
    try {
        session.db = 'test_db';
        session.uid = 99;
        removeColumnWidth('product', 'name');
        expect(getColumnWidth('product', 'name')).toBe(null);
        setColumnWidth('product', 'name', '180');
        expect(getColumnWidth('product', 'name')).toBe('180');
        removeColumnWidth('product', 'name');
        expect(getColumnWidth('product', 'name')).toBe(null);
    } finally {
        session.db = realDb;
        session.uid = realUid;
        browser.localStorage.clear();
    }
});

test.tags('muk_web_list_column');
test('column width is persisted on the drag-end pointerup, not the initial pointerdown', async () => {
    const realDb = session.db;
    const realUid = session.uid;
    const th = document.createElement('th');
    document.body.appendChild(th);
    try {
        session.db = 'test_db';
        session.uid = 99;
        th.style.width = '240px';
        th.dataset.name = 'name';
        const handle = document.createElement('span');
        th.appendChild(handle);
        removeColumnWidth('product', 'name');
        const renderer = {
            columnWidths: { onStartResize() {} },
            props: { list: { resModel: 'product' } },
        };
        ListRenderer.prototype.onStartResizeWithSave.call(renderer, {
            target: handle,
        });
        window.dispatchEvent(new PointerEvent('pointerdown', { button: 0 }));
        expect(getColumnWidth('product', 'name')).toBe(null);
        window.dispatchEvent(new PointerEvent('pointerup'));
        expect(getColumnWidth('product', 'name')).toBe('240px');
    } finally {
        session.db = realDb;
        session.uid = realUid;
        th.remove();
        browser.localStorage.clear();
    }
});
