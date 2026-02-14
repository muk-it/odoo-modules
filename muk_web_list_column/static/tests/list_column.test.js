import { session } from "@web/session";
import { browser } from "@web/core/browser/browser";
import { expect, test } from "@odoo/hoot";

import {
    getColumnWidth,
    removeColumnWidth,
    setColumnWidth,
} from "@muk_web_list_column/views/list/list_view_storage";

test.tags("muk_web_list_column");
test("column width is stored and restored from localStorage", async () => {
    const realDb = session.db;
    const realUid = session.uid;
    try {
        session.db = "test_db";
        session.uid = 99;
        removeColumnWidth("product", "name");
        expect(getColumnWidth("product", "name")).toBe(null);
        setColumnWidth("product", "name", "180");
        expect(getColumnWidth("product", "name")).toBe("180");
        removeColumnWidth("product", "name");
        expect(getColumnWidth("product", "name")).toBe(null);
    } finally {
        session.db = realDb;
        session.uid = realUid;
        browser.localStorage.clear();
    }
});
