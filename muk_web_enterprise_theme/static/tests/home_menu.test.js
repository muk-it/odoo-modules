import { user } from '@web/core/user';
import { cookie } from '@web/core/browser/cookie';
import { expect, mockMatchMedia, test } from '@odoo/hoot';

import {
    destroyApp,
    mountWithCleanup,
    patchWithCleanup,
} from '@web/../tests/web_test_helpers';

import { defineMailModels } from '@mail/../tests/mail_test_helpers';
import { HomeMenu } from '@web_enterprise/webclient/home_menu/home_menu';

defineMailModels();

async function mountHomeMenu(colorScheme, company) {
    cookie.set('color_scheme', colorScheme);
    mockMatchMedia({ 'prefers-color-scheme': colorScheme });
    patchWithCleanup(user, {
        get activeCompany() {
            return { id: 3, ...company };
        },
    });
    await mountWithCleanup(HomeMenu, {
        props: { apps: [], reorderApps: () => {} },
    });
}

for (const colorScheme of ['light', 'dark']) {
    test.tags('muk_web_enterprise_theme');
    test(`home menu shows the ${colorScheme} company background image`, async () => {
        await mountHomeMenu(colorScheme, {
            has_background_image_light: true,
            has_background_image_dark: true,
        });
        const style = document.querySelector('.o_home_menu').style.backgroundImage;
        expect(style).toInclude(`field=background_image_${colorScheme}`);
        expect(style).toInclude('id=3');
        expect(document.body).toHaveClass('o_home_menu_background_custom');
        destroyApp();
        expect(document.body).not.toHaveClass('o_home_menu_background_custom');
    });
}

test.tags('muk_web_enterprise_theme');
test('home menu keeps the default background without an image for the scheme', async () => {
    await mountHomeMenu('dark', { has_background_image_light: true });
    expect('.o_home_menu').not.toHaveAttribute('style');
    expect(document.body).not.toHaveClass('o_home_menu_background_custom');
});
