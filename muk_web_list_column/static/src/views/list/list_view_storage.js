import { session } from '@web/session';
import { user } from '@web/core/user';
import { browser } from '@web/core/browser/browser';

/**
 * Build the localStorage key scoping a column width to db, model, column and user.
 * @param {string} resModel technical model name
 * @param {string} columnName column name
 * @returns {string}
 */
function getColumnWidthKey(resModel, columnName) {
    return `muk_web_list_column.columnWidth:${session.db},${resModel},${columnName},${user.userId}`;
}

/**
 * Read the stored width for a column, or null when none was saved.
 * @param {string} resModel technical model name
 * @param {string} columnName column name
 * @returns {string|null}
 */
export function getColumnWidth(resModel, columnName) {
    return browser.localStorage.getItem(getColumnWidthKey(resModel, columnName));
}

/**
 * Persist the width for a column in localStorage.
 * @param {string} resModel technical model name
 * @param {string} columnName column name
 * @param {string} width width value to store
 */
export function setColumnWidth(resModel, columnName, width) {
    browser.localStorage.setItem(getColumnWidthKey(resModel, columnName), width);
}

/**
 * Remove the stored width for a column from localStorage.
 * @param {string} resModel technical model name
 * @param {string} columnName column name
 */
export function removeColumnWidth(resModel, columnName) {
    browser.localStorage.removeItem(getColumnWidthKey(resModel, columnName));
}
