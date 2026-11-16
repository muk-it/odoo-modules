/** @odoo-module */

import { _t } from '@muk_ai/core/compat/translation';

import { describeToolBlock, toolBlockDecorators } from '@muk_ai/chat/session/turns';

/**
 * Describe a browser tool card in plain language.
 * @param {string} icon the card icon
 * @param {Function} label the card label, translated when the card renders
 * @param {Function} [band] the line beside it, `({args}) => text`
 * @returns {object} the `describeToolBlock` parts
 */
function browserTool(icon, label, band = ({ args }) => args.element || '') {
    return { icon: () => icon, label, band };
}

/**
 * Return the host of a URL, or the URL when it does not parse.
 * @param {string} url the URL
 * @returns {string} the host
 */
function host(url) {
    try {
        return new URL(url).host;
    } catch {
        return url || '';
    }
}

const browserTools = {
    browser_read_page: browserTool(
        'fa-eye',
        () => _t('Read the page'),
        () => '',
    ),
    browser_find: browserTool(
        'fa-search',
        () => _t('Find on the page'),
        ({ args }) => (args.query ? `"${args.query}"` : ''),
    ),
    browser_screenshot: browserTool('fa-camera', () => _t('Take a screenshot')),
    browser_scroll: browserTool(
        'fa-arrows-v',
        () => _t('Scroll the page'),
        ({ args }) => args.direction || '',
    ),
    browser_wait_for: browserTool(
        'fa-hourglass-half',
        () => _t('Wait for the page'),
        ({ args }) => args.text || args.text_gone || '',
    ),
    browser_tabs: browserTool(
        'fa-external-link',
        () => _t('Manage tabs'),
        ({ args }) => args.action || '',
    ),
    browser_click: browserTool('fa-mouse-pointer', () => _t('Click')),
    browser_type: browserTool(
        'fa-keyboard-o',
        () => _t('Type'),
        ({ args }) =>
            [args.element, args.text && `"${args.text}"`].filter(Boolean).join(': '),
    ),
    browser_fill_form: browserTool(
        'fa-check-square-o',
        () => _t('Fill a form'),
        ({ args }) => _t('%s fields', (args.fields || []).length),
    ),
    browser_select_option: browserTool('fa-caret-square-o-down', () =>
        _t('Choose an option'),
    ),
    browser_press_key: browserTool(
        'fa-keyboard-o',
        () => _t('Press a key'),
        ({ args }) => args.key || '',
    ),
    browser_hover: browserTool('fa-hand-pointer-o', () => _t('Point at')),
    browser_navigate: browserTool(
        'fa-map-o',
        () => _t('Open a page'),
        ({ args }) => host(args.url),
    ),
    browser_navigate_back: browserTool(
        'fa-arrow-left',
        () => _t('Go back'),
        () => '',
    ),
    browser_save_file: browserTool(
        'fa-download',
        () => _t('Save a file to Odoo'),
        ({ args }) => args.name || args.element || host(args.url),
    ),
    browser_upload_file: browserTool('fa-upload', () => _t('Upload a file')),
    browser_propose_plan: browserTool(
        'fa-list-ol',
        () => _t('Propose a plan'),
        ({ args }) => (args.origins || []).map(host).join(', '),
    ),
};

toolBlockDecorators.add('muk_ai_browser.browser_tools', (block) => {
    if (browserTools[block.name]) {
        describeToolBlock(block, browserTools[block.name]);
    }
});
