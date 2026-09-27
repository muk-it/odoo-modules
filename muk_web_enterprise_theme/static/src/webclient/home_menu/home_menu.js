import { user } from '@web/core/user';
import { url } from '@web/core/utils/urls';
import { patch } from '@web/core/utils/patch';
import { cookie } from '@web/core/browser/cookie';
import { onMounted, onWillUnmount } from '@odoo/owl';

import { HomeMenu } from '@web_enterprise/webclient/home_menu/home_menu';

/** Show the active company background image of the current color scheme. */
patch(HomeMenu.prototype, {
    setup() {
        super.setup();
        const scheme = cookie.get('color_scheme') === 'dark' ? 'dark' : 'light';
        const company = user.activeCompany;
        this.backgroundImageUrl =
            company[`has_background_image_${scheme}`] &&
            url('/web/image', {
                model: 'res.company',
                field: `background_image_${scheme}`,
                id: company.id,
            });
        onMounted(() => {
            document.body.classList.toggle(
                'o_home_menu_background_custom',
                Boolean(this.backgroundImageUrl),
            );
        });
        onWillUnmount(() => {
            document.body.classList.remove('o_home_menu_background_custom');
        });
    },
});
