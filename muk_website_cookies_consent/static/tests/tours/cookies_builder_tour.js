import { registerWebsitePreviewTour } from '@website/js/tours/tour_utils';
import { rpc } from '@web/core/network/rpc';

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
        trigger:
            ".o_customize_tab [data-label='Layout'] .dropdown-toggle:contains('Bar at the bottom')",
    },
    {
        content: 'Open the layout choices',
        trigger: ".o_customize_tab [data-label='Layout'] .dropdown-toggle",
        run: 'click',
    },
    {
        content: 'Passing over a layout decides nothing',
        trigger: ".o_popover .o-dropdown-item:contains('Centred dialog')",
        run: 'hover',
    },
    {
        content: 'So the website still holds the layout it had',
        trigger: ".o_popover .o-dropdown-item:contains('Centred dialog')",
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
        trigger: ".o_popover .o-dropdown-item:contains('Centred dialog')",
        run: 'click',
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
    {
        content: 'Open the density choices',
        trigger: ".o_customize_tab [data-label='Density'] .dropdown-toggle",
        run: 'click',
    },
    {
        content: 'Trim the notice',
        trigger: ".o_popover .o-dropdown-item:contains('Compact')",
        run: 'click',
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
        trigger: ".o_customize_tab [data-label='Footer Link'] input[type='checkbox']",
        run: 'click',
    },
    showTheBanner('Show the banner after the footer link was turned off'),
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
    {
        content: 'Open the floating button choices',
        trigger: ".o_customize_tab [data-label='Floating Button'] .dropdown-toggle",
        run: 'click',
    },
    {
        content: 'Move it to the other corner',
        trigger: ".o_popover .o-dropdown-item:contains('Bottom left')",
        run: 'click',
    },
    showTheBanner('Show the banner once the corner has changed'),
    {
        content: 'The button is rendered in the corner the editor picked',
        trigger:
            ".o_customize_tab [data-label='Floating Button'] .dropdown-toggle:contains('Bottom left')",
        async run() {
            const stored = await storedBanner();
            if (stored.cookie_reopen_float !== 'left') {
                throw new Error('The chosen corner was not stored.');
            }
            const rendered = [...document.querySelectorAll('iframe')].some((el) =>
                el.contentDocument?.querySelector(
                    '.mk_cookies_float.mk_cookies_float_left',
                ),
            );
            if (!rendered) {
                throw new Error('The button was not rendered in that corner.');
            }
        },
    },
]);
