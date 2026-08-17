/** @odoo-module **/

import wTourUtils from '@website/js/tours/tour_utils';

const OPTION = '.snippet-option-MukCookiesBar';

// ----------------------------------------------------------
// Helper
// ----------------------------------------------------------

/**
 * Read the banner settings straight off the website record.
 * @returns {Promise<object>} the stored layout and density
 */
async function storedBanner() {
    const response = await fetch('/web/dataset/call_kw', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            jsonrpc: '2.0',
            method: 'call',
            params: {
                model: 'website',
                method: 'search_read',
                args: [
                    [],
                    [
                        'cookie_layout',
                        'cookie_density',
                        'cookie_reopen_footer',
                        'cookie_reopen_float',
                    ],
                ],
                kwargs: { limit: 1 },
            },
        }),
    });
    const [values] = (await response.json()).result;
    return values;
}

/**
 * Build the step that reveals the banner from the invisible elements panel.
 * @param {string} content the step description shown while it runs
 * @returns {object} the tour step
 */
function showTheBanner(content) {
    return {
        content,
        trigger: '.o_we_invisible_el_panel .o_we_invisible_entry',
        in_modal: false,
        run: 'click',
    };
}

/**
 * Build the step that opens one of the option's dropdowns.
 * @param {string} content the step description shown while it runs
 * @param {string} attribute the data attribute its items carry
 * @returns {object} the tour step
 */
function openChoices(content, attribute) {
    return {
        content,
        trigger: `${OPTION} we-select:has(we-button[data-${attribute}]) we-toggler`,
        in_modal: false,
        run: 'click',
    };
}

// ----------------------------------------------------------
// Tours
// ----------------------------------------------------------

wTourUtils.registerWebsitePreviewTour(
    'muk_cookies_builder',
    { url: '/', edition: true },
    () => [
        showTheBanner('Show the banner, which is hidden once a decision was taken'),
        {
            content: 'The option is offered even though the banner is not editable',
            trigger: `${OPTION} we-select:has(we-button[data-select-cookie-layout]) we-toggler:contains('Bar at the bottom')`,
            in_modal: false,
            run: () => {},
            isCheck: true,
        },
        openChoices('Open the layout choices', 'select-cookie-layout'),
        {
            content: 'Passing over a layout decides nothing',
            trigger: `${OPTION} we-button[data-select-cookie-layout='center']`,
            in_modal: false,
            run: () => {
                // this branch has no hover helper, and the preview a hover
                // would trigger is what the next step proves never happened
                const itemEl = document.querySelector(
                    `${OPTION} we-button[data-select-cookie-layout='center']`,
                );
                itemEl.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                itemEl.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
            },
        },
        {
            content: 'So the website still holds the layout it had',
            trigger: `${OPTION} we-button[data-select-cookie-layout='center']`,
            in_modal: false,
            async run() {
                const stored = await storedBanner();
                if (stored.cookie_layout !== 'bar_bottom') {
                    throw new Error(
                        `Hovering wrote "${stored.cookie_layout}" to the website, ` +
                            'where only a click may.',
                    );
                }
            },
        },
    ],
);
