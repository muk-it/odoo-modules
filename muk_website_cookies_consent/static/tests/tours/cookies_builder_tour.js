import { registerWebsitePreviewTour } from '@website/js/tours/tour_utils';
import { rpc } from '@web/core/network/rpc';

const OPTION = '.snippet-option-MukCookiesBar';

// ----------------------------------------------------------
// Helper
// ----------------------------------------------------------

/**
 * Read the banner settings straight off the website record.
 * @returns {Promise<object>} the stored layout and density
 */
async function storedBanner() {
    const [values] = await rpc('/web/dataset/call_kw', {
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
    });
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
        async run() {
            // The entry toggles, so clicking it blindly hides a banner
            // the editor already restored after its reload, and with it
            // the selection its option panel hangs off.
            for (let attempt = 0; attempt < 10; attempt++) {
                const banner = [...document.querySelectorAll('iframe')]
                    .map((el) =>
                        el.contentDocument?.querySelector('#website_cookies_bar'),
                    )
                    .find(Boolean);
                const shown = banner && !banner.dataset.invisible;
                if (shown && document.querySelector('.snippet-option-MukCookiesBar')) {
                    return;
                }
                document
                    .querySelector('.o_we_invisible_el_panel .o_we_invisible_entry')
                    ?.click();
                await new Promise((resolve) => setTimeout(resolve, 300));
            }
            throw new Error('The banner would not stay revealed for its option.');
        },
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
        run: 'click',
    };
}

// ----------------------------------------------------------
// Tours
// ----------------------------------------------------------

registerWebsitePreviewTour('muk_cookies_builder', { url: '/', edition: true }, () => [
    showTheBanner('Show the banner, which is hidden once a decision was taken'),
    {
        content: 'The option is offered even though the banner is not editable',
        trigger: `${OPTION} we-select:has(we-button[data-select-cookie-layout]) we-toggler:contains('Bar at the bottom')`,
    },
    openChoices('Open the layout choices', 'select-cookie-layout'),
    {
        content: 'Passing over a layout decides nothing',
        trigger: `${OPTION} we-button[data-select-cookie-layout='center']`,
        run: 'hover',
    },
    {
        content: 'So the website still holds the layout it had',
        trigger: `${OPTION} we-button[data-select-cookie-layout='center']`,
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
    {
        content: 'Choose the centred dialog',
        trigger: `${OPTION} we-button[data-select-cookie-layout='center']`,
        run: 'click',
    },
    {
        content: 'Wait for the editor to reload with the stored layout',
        trigger: ':iframe #website_cookies_bar .mk_cookies_center:not(:visible)',
    },
    showTheBanner('Show the banner again, once the editor has reloaded'),
    {
        content: 'The layout is rendered from the website, not swapped in place',
        trigger: ':iframe #website_cookies_bar .mk_cookies_center.s_popup_middle',
        async run() {
            const stored = await storedBanner();
            if (stored.cookie_layout !== 'center') {
                throw new Error('The chosen layout was not stored.');
            }
        },
    },
    openChoices('Open the density choices', 'select-cookie-density'),
    {
        content: 'Trim the notice',
        trigger: `${OPTION} we-button[data-select-cookie-density='compact']`,
        run: 'click',
    },
    {
        content: 'Wait for the editor to reload with the stored density',
        trigger:
            ':iframe #website_cookies_bar .mk_cookies_density_compact:not(:visible)',
    },
    showTheBanner('Show the banner once more'),
    {
        content: 'Choosing a density leaves the layout and its position alone',
        trigger:
            ':iframe #website_cookies_bar .mk_cookies_density_compact.mk_cookies_center.s_popup_middle',
        async run() {
            const stored = await storedBanner();
            if (stored.cookie_layout !== 'center') {
                throw new Error(
                    `Choosing a density moved the layout to "${stored.cookie_layout}".`,
                );
            }
            if (stored.cookie_density !== 'compact') {
                throw new Error('The chosen density was not stored.');
            }
        },
    },
    {
        content: 'The way back to the choice is offered here too',
        trigger: `${OPTION} we-button[data-toggle-cookie-footer] we-checkbox`,
        run: 'click',
    },
    {
        content: 'Turning the footer link off is stored and takes the link away',
        trigger: ':iframe body:not(:has(.mk_cookies_footer))',
        async run() {
            const stored = await storedBanner();
            if (stored.cookie_reopen_footer) {
                throw new Error('The footer link was left on.');
            }
        },
    },
    showTheBanner('Show the banner after the footer link was turned off'),
    openChoices('Open the floating button choices', 'select-cookie-float'),
    {
        content: 'Move it to the other corner',
        trigger: `${OPTION} we-button[data-select-cookie-float='left']`,
        run: 'click',
    },
    {
        content: 'Wait for the editor to reload with the stored corner',
        trigger: ':iframe .mk_cookies_float.mk_cookies_float_left',
    },
    showTheBanner('Show the banner once the corner has changed'),
    {
        content: 'The button is rendered in the corner the editor picked',
        trigger: `${OPTION} we-select:has(we-button[data-select-cookie-float])`,
        async run() {
            const stored = await storedBanner();
            if (stored.cookie_reopen_float !== 'left') {
                throw new Error('The chosen corner was not stored.');
            }
        },
    },
]);
