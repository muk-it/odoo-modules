import { beforeEach, describe, expect, test } from '@odoo/hoot';
import { press, queryAllTexts, queryOne } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';

import { user } from '@web/core/user';
import { NavBar } from '@web/webclient/navbar/navbar';

import {
    contains,
    defineMenus,
    getMockEnv,
    getService,
    mockService,
    mountWithCleanup,
    patchWithCleanup,
} from '@web/../tests/web_test_helpers';

import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import '@muk_web_appsbar/webclient/menus/app_menu_service';
import '@muk_web_theme/webclient/navbar/navbar';

describe.current.tags('desktop');
defineMailModels();

let paletteCalls;

function patchActiveCompany(values) {
    patchWithCleanup(user, {
        get activeCompany() {
            return { id: 5, ...values };
        },
    });
}

async function openAppsMenu() {
    await mountWithCleanup(NavBar);
    await contains('.o_navbar_apps_menu button.dropdown-toggle').click();
}

beforeEach(() => {
    patchActiveCompany({ has_background_image: false });
    defineMenus([
        { id: 1, name: 'Alpha', xmlid: 'app.alpha', actionID: 339 },
        { id: 2, name: 'Beta', xmlid: 'app.beta', actionID: 12 },
    ]);
    paletteCalls = [];
    mockService('command', {
        openMainPalette(config, onClose) {
            paletteCalls.push({ config, onClose });
        },
    });
});

test.tags('muk_web_theme');
test('apps menu lists every app with its icon, label and href', async () => {
    await openAppsMenu();
    expect('.mk_app_menu .o_app').toHaveCount(2);
    expect('.mk_app_menu .mk_app_icon').toHaveCount(2);
    expect(queryAllTexts('.mk_app_menu .mk_app_name')).toEqual(['Alpha', 'Beta']);
    expect('.mk_app_menu .o_app:first').toHaveAttribute('href', '/odoo/action-339');
    expect('.mk_app_menu .o_app:first').toHaveAttribute('data-menu-xmlid', 'app.alpha');
});

test.tags('muk_web_theme');
test('clicking an app selects its menu', async () => {
    const selected = [];
    await mountWithCleanup(NavBar);
    patchWithCleanup(getService('menu'), {
        selectMenu(menu) {
            selected.push(menu.id);
        },
    });
    await contains('.o_navbar_apps_menu button.dropdown-toggle').click();
    await contains('.mk_app_menu .o_app:contains(Beta)').click();
    expect(selected).toEqual([2]);
});

test.tags('muk_web_theme');
test('apps menu background follows the company image', async () => {
    patchActiveCompany({ has_background_image: true });
    await openAppsMenu();
    const background = queryOne('.mk_app_menu').style.backgroundImage;
    expect(background).toInclude('/web/image');
    expect(background).toInclude('background_image');
    expect(background).toInclude('id=5');
});

test.tags('muk_web_theme');
test('apps menu falls back to the bundled background image', async () => {
    await openAppsMenu();
    expect(queryOne('.mk_app_menu').style.backgroundImage).toInclude(
        '/muk_web_theme/static/src/webclient/appsmenu/background.png',
    );
});

test.tags('muk_web_theme');
test('typing in the open apps menu opens the command palette once', async () => {
    await openAppsMenu();
    await press('s');
    await press('a');
    await animationFrame();
    expect(paletteCalls).toHaveLength(1);
    expect(paletteCalls[0].config.searchValue).toBe('/s');
    paletteCalls[0].onClose();
    await press('b');
    await animationFrame();
    expect(paletteCalls).toHaveLength(2);
    expect(paletteCalls[1].config.searchValue).toBe('/b');
});

test.tags('muk_web_theme');
test('shortcuts and keys outside the apps menu leave the palette closed', async () => {
    await mountWithCleanup(NavBar);
    await press('s');
    await contains('.o_navbar_apps_menu button.dropdown-toggle').click();
    await press(['ctrl', 'p']);
    await animationFrame();
    expect(paletteCalls).toHaveLength(0);
});

test.tags('muk_web_theme');
test('the apps menu closes when the action manager updates the ui', async () => {
    await openAppsMenu();
    expect('.mk_app_menu').toHaveCount(1);
    getMockEnv().bus.trigger('ACTION_MANAGER:UI-UPDATED');
    await animationFrame();
    expect('.mk_app_menu').toHaveCount(0);
});
