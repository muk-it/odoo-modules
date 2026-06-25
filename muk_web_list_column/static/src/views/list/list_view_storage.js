import { session } from '@web/session';
import { browser } from '@web/core/browser/browser';

/**
 * Build the localStorage key scoping a column width to db, model, field, user and view.
 * @param {string} resModel technical model name
 * @param {string} fieldName column field name
 * @param {string} [viewId] optional view identifier
 * @returns {string}
 */
function getColumnWidthKey(resModel, fieldName, viewId) {
    const parts = [session.db, resModel, fieldName, session.uid, viewId];
    const key = parts.reduce((key, part) => key + ',' + part);
    return `muk_web_list_column.columnWidth:${key}`;
}

/**
 * Read the stored width for a column, or null when none was saved.
 * @param {string} resModel technical model name
 * @param {string} fieldName column field name
 * @returns {string|null}
 */
export function getColumnWidth(resModel, fieldName) {
    const key = getColumnWidthKey(resModel, fieldName);
    return browser.localStorage.getItem(key);
}

/**
 * Persist the width for a column in localStorage.
 * @param {string} resModel technical model name
 * @param {string} fieldName column field name
 * @param {string} data width value to store
 */
export function setColumnWidth(resModel, fieldName, data) {
    const key = getColumnWidthKey(resModel, fieldName);
    return browser.localStorage.setItem(key, data);
}

/**
 * Remove the stored width for a column from localStorage.
 * @param {string} resModel technical model name
 * @param {string} fieldName column field name
 * @param {string} [viewId] optional view identifier
 */
export function removeColumnWidth(resModel, fieldName, viewId) {
    const key = getColumnWidthKey(resModel, fieldName, viewId);
    return browser.localStorage.removeItem(key);
}
