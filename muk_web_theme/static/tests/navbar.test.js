import { beforeEach, describe, expect, test } from '@odoo/hoot';
import { queryAllTexts } from '@odoo/hoot-dom';

import { user } from '@web/core/user';
import { NavBar } from '@web/webclient/navbar/navbar';

import {
    contains,
    defineMenus,
    mountWithCleanup,
    patchWithCleanup,
} from '@web/../tests/web_test_helpers';

import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import '@muk_web_appsbar/webclient/menus/app_menu_service';
import '@muk_web_theme/webclient/navbar/navbar';

describe.current.tags('desktop');
defineMailModels();

beforeEach(() => {
    patchWithCleanup(user, {
        get activeCompany() {
            return { id: 1, has_background_image: false };
        },
    });
});

test.tags('muk_web_theme');
test('apps menu lists every app with its label', async () => {
    defineMenus([
        { id: 1, name: 'Alpha', xmlid: 'app.alpha', actionID: 11 },
        { id: 2, name: 'Beta', xmlid: 'app.beta', actionID: 12 },
    ]);
    await mountWithCleanup(NavBar);
    await contains('.o_navbar_apps_menu button.dropdown-toggle').click();
    expect('.mk_app_menu').toHaveCount(1);
    expect('.mk_app_menu .o_app').toHaveCount(2);
    expect(queryAllTexts('.mk_app_menu .mk_app_name')).toEqual(['Alpha', 'Beta']);
});

test.tags('muk_web_theme');
test('apps menu keeps the action href on each app', async () => {
    defineMenus([{ id: 1, name: 'Alpha', xmlid: 'app.alpha', actionID: 339 }]);
    await mountWithCleanup(NavBar);
    await contains('.o_navbar_apps_menu button.dropdown-toggle').click();
    expect('.mk_app_menu .o_app').toHaveAttribute('href', '/odoo/action-339');
    expect('.mk_app_menu .o_app').toHaveAttribute('data-menu-xmlid', 'app.alpha');
});

test.tags('muk_web_theme');
test('apps menu renders one icon and label per app', async () => {
    defineMenus([{ id: 1, name: 'Alpha', xmlid: 'app.alpha', actionID: 11 }]);
    await mountWithCleanup(NavBar);
    await contains('.o_navbar_apps_menu button.dropdown-toggle').click();
    expect('.mk_app_menu .o_app').toHaveCount(1);
    expect('.mk_app_menu .mk_app_icon').toHaveCount(1);
    expect('.mk_app_menu .mk_app_name').toHaveText('Alpha');
});

test.tags('muk_web_theme');
test('apps menu toggles closed again', async () => {
    defineMenus([{ id: 1, name: 'Alpha', xmlid: 'app.alpha', actionID: 11 }]);
    await mountWithCleanup(NavBar);
    await contains('.o_navbar_apps_menu button.dropdown-toggle').click();
    expect('.mk_app_menu').toHaveCount(1);
    await contains('.o_navbar_apps_menu button.dropdown-toggle').click();
    expect('.mk_app_menu').toHaveCount(0);
});
