import { describe, expect, test } from '@odoo/hoot';
import { press, queryOne } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';

import { user } from '@web/core/user';
import { NavBar } from '@web/webclient/navbar/navbar';

import {
    contains,
    defineMenus,
    getMockEnv,
    mockService,
    mountWithCleanup,
    patchWithCleanup,
} from '@web/../tests/web_test_helpers';

import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import '@muk_web_appsbar/webclient/menus/app_menu_service';
import '@muk_web_theme/webclient/navbar/navbar';

describe.current.tags('desktop');
defineMailModels();

const MENUS = [{ id: 1, name: 'Alpha', xmlid: 'app.alpha', actionID: 11 }];

function patchActiveCompany(values) {
    patchWithCleanup(user, {
        get activeCompany() {
            return { id: 5, ...values };
        },
    });
}

async function openAppsMenu() {
    defineMenus(MENUS);
    await mountWithCleanup(NavBar);
    await contains('.o_navbar_apps_menu button.dropdown-toggle').click();
}

test.tags('muk_web_theme');
test('apps menu uses the company background image when one is set', async () => {
    patchActiveCompany({ has_background_image: true });
    await openAppsMenu();
    const background = queryOne('.mk_app_menu').style.backgroundImage;
    expect(background).toInclude('/web/image');
    expect(background).toInclude('background_image');
    expect(background).toInclude('id=5');
});

test.tags('muk_web_theme');
test('apps menu falls back to the bundled background image', async () => {
    patchActiveCompany({ has_background_image: false });
    await openAppsMenu();
    expect(queryOne('.mk_app_menu').style.backgroundImage).toInclude(
        '/muk_web_theme/static/src/img/background.png',
    );
});

test.tags('muk_web_theme');
test('typing a printable key in the apps menu opens the command palette', async () => {
    patchActiveCompany({ has_background_image: false });
    const calls = [];
    mockService('command', {
        openMainPalette(config, onClose) {
            calls.push({ config, onClose });
        },
    });
    await openAppsMenu();
    await press('s');
    await animationFrame();
    expect(calls).toHaveLength(1);
    expect(calls[0].config.searchValue).toBe('/s');
});

test.tags('muk_web_theme');
test('the command palette is only opened once per apps menu session', async () => {
    patchActiveCompany({ has_background_image: false });
    const calls = [];
    mockService('command', {
        openMainPalette(config, onClose) {
            calls.push({ config, onClose });
        },
    });
    await openAppsMenu();
    await press('s');
    await press('a');
    await animationFrame();
    expect(calls).toHaveLength(1);
    calls[0].onClose();
    await press('b');
    await animationFrame();
    expect(calls).toHaveLength(2);
    expect(calls[1].config.searchValue).toBe('/b');
});

test.tags('muk_web_theme');
test('a control shortcut does not open the command palette', async () => {
    patchActiveCompany({ has_background_image: false });
    const calls = [];
    mockService('command', {
        openMainPalette(config) {
            calls.push(config);
        },
    });
    await openAppsMenu();
    await press(['ctrl', 'p']);
    await animationFrame();
    expect(calls).toHaveLength(0);
});

test.tags('muk_web_theme');
test('a keystroke outside the apps menu does not open the command palette', async () => {
    patchActiveCompany({ has_background_image: false });
    const calls = [];
    mockService('command', {
        openMainPalette(config) {
            calls.push(config);
        },
    });
    defineMenus(MENUS);
    await mountWithCleanup(NavBar);
    await press('s');
    await animationFrame();
    expect(calls).toHaveLength(0);
});

test.tags('muk_web_theme');
test('the apps menu closes when the action manager updates the ui', async () => {
    patchActiveCompany({ has_background_image: false });
    await openAppsMenu();
    expect('.mk_app_menu').toHaveCount(1);
    getMockEnv().bus.trigger('ACTION_MANAGER:UI-UPDATED');
    await animationFrame();
    expect('.mk_app_menu').toHaveCount(0);
});
