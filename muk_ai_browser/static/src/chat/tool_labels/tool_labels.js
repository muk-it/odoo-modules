import { _t } from '@web/core/l10n/translation';

import { toolLabels } from '@muk_ai/chat/tool_card/tool_labels';

/**
 * Describe a browser tool card in plain language.
 * @param {string} icon the card icon
 * @param {string} label the card label
 * @param {Function} [band] the line beside it, `({args}) => text`
 * @returns {object} the `describeToolBlock` parts
 */
function browserTool(icon, label, band = ({ args }) => args.element || '') {
    return { icon: () => icon, label: () => label, band };
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

Object.assign(toolLabels, {
    browser_read_page: browserTool('visibility', _t('Read the page'), () => ''),
    browser_find: browserTool('search', _t('Find on the page'), ({ args }) =>
        args.query ? `"${args.query}"` : '',
    ),
    browser_screenshot: browserTool('photo_camera', _t('Take a screenshot')),
    browser_scroll: browserTool(
        'swap_vert',
        _t('Scroll the page'),
        ({ args }) => args.direction || '',
    ),
    browser_wait_for: browserTool(
        'hourglass_empty',
        _t('Wait for the page'),
        ({ args }) => args.text || args.text_gone || '',
    ),
    browser_tabs: browserTool(
        'open_in_new',
        _t('Manage tabs'),
        ({ args }) => args.action || '',
    ),
    browser_click: browserTool('mouse', _t('Click')),
    browser_type: browserTool('keyboard', _t('Type'), ({ args }) =>
        [args.element, args.text && `"${args.text}"`].filter(Boolean).join(': '),
    ),
    browser_fill_form: browserTool('checklist', _t('Fill a form'), ({ args }) =>
        _t('%s fields', (args.fields || []).length),
    ),
    browser_select_option: browserTool(
        'arrow_drop_down_circle',
        _t('Choose an option'),
    ),
    browser_press_key: browserTool(
        'keyboard',
        _t('Press a key'),
        ({ args }) => args.key || '',
    ),
    browser_hover: browserTool('back_hand', _t('Point at')),
    browser_navigate: browserTool('map', _t('Open a page'), ({ args }) =>
        host(args.url),
    ),
    browser_navigate_back: browserTool('arrow_back', _t('Go back'), () => ''),
    browser_propose_plan: browserTool('assignment', _t('Propose a plan'), ({ args }) =>
        (args.origins || []).map(host).join(', '),
    ),
});
