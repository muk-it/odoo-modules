import { user } from '@web/core/user';
import { url } from '@web/core/utils/urls';
import { patch } from '@web/core/utils/patch';
import { cookie } from '@web/core/browser/cookie';
import { onMounted, onWillUnmount } from '@odoo/owl';

import { HomeMenu } from '@web_enterprise/webclient/home_menu/home_menu';

/**
 * Build the apps menu background image URL for a company and color scheme.
 * @param {object} company the active company record
 * @param {string} colorScheme the active color scheme, e.g. "dark"
 * @returns {string|null} the image URL, or null when no matching image is set
 */
export function getCompanyBackgroundImageUrl(company, colorScheme) {
    if (colorScheme === 'dark' && company?.has_background_image_dark) {
        return url('/web/image', {
            model: 'res.company',
            field: 'background_image_dark',
            id: company.id,
        });
    }
    if (colorScheme !== 'dark' && company?.has_background_image_light) {
        return url('/web/image', {
            model: 'res.company',
            field: 'background_image_light',
            id: company.id,
        });
    }
    return null;
}

/** Apply the company background image to the home menu on mount. */
patch(HomeMenu.prototype, {
    setup() {
        super.setup();

        const backgroundImageUrl = getCompanyBackgroundImageUrl(
            user.activeCompany,
            cookie.get('color_scheme'),
        );
        if (backgroundImageUrl) {
            this.backgroundImageUrl = backgroundImageUrl;
        }
        onMounted(() => {
            document.body.classList.toggle(
                'o_home_menu_background_custom',
                this.backgroundImageUrl,
            );
        });
        onWillUnmount(() => {
            document.body.classList.remove('o_home_menu_background_custom');
        });
    },
});
