import { user } from '@web/core/user';
import { expect, test } from '@odoo/hoot';
import { animationFrame } from '@odoo/hoot-mock';

import {
    contains,
    getMockEnv,
    mockService,
    mountWithCleanup,
    patchWithCleanup,
} from '@web/../tests/web_test_helpers';

import { AppsBar } from '@muk_web_appsbar/webclient/appsbar/appsbar';

const APPS = [
    { id: 1, xmlid: 'app.alpha', label: 'Alpha', href: '/odoo/alpha' },
    { id: 2, xmlid: 'app.beta', label: 'Beta', href: '/odoo/beta' },
];

function patchActiveCompany(values) {
    const company = { ...user.activeCompany, id: 1, ...values };
    patchWithCleanup(user, {
        get activeCompany() {
            return company;
        },
    });
}

function mockAppMenu({ apps = APPS, currentApp = null, onSelectApp = () => {} } = {}) {
    const state = { apps, currentApp };
    mockService('app_menu', {
        getAppsMenuItems: () => state.apps,
        getCurrentApp: () => state.currentApp,
        selectApp: onSelectApp,
    });
    return state;
}

test.tags('muk_web_appsbar');
test('appsbar renders one entry per app with its label and href', async () => {
    patchActiveCompany({ has_appsbar_image: false });
    mockAppMenu();
    await mountWithCleanup(AppsBar);
    expect('.mk_apps_sidebar_menu .nav-link').toHaveCount(2);
    expect('.mk_apps_sidebar_name:first').toHaveText('Alpha');
    expect('.mk_apps_sidebar_menu .nav-link:first').toHaveAttribute(
        'href',
        '/odoo/alpha',
    );
    expect('.mk_apps_sidebar_menu .nav-link:first').toHaveAttribute(
        'data-menu-xmlid',
        'app.alpha',
    );
});

test.tags('muk_web_appsbar');
test('appsbar marks the current app as active', async () => {
    patchActiveCompany({ has_appsbar_image: false });
    mockAppMenu({ currentApp: { id: 2 } });
    await mountWithCleanup(AppsBar);
    expect('.nav-item.active').toHaveCount(1);
    expect('.nav-item.active .mk_apps_sidebar_name').toHaveText('Beta');
});

test.tags('muk_web_appsbar');
test('appsbar marks no app active when none is current', async () => {
    patchActiveCompany({ has_appsbar_image: false });
    mockAppMenu({ currentApp: null });
    await mountWithCleanup(AppsBar);
    expect('.nav-item').toHaveCount(2);
    expect('.nav-item.active').toHaveCount(0);
});

test.tags('muk_web_appsbar');
test('appsbar renders exactly one icon per app', async () => {
    patchActiveCompany({ has_appsbar_image: false });
    mockAppMenu({
        apps: [
            { id: 1, xmlid: 'app.alpha', label: 'Alpha', href: '/odoo/alpha' },
            {
                id: 2,
                xmlid: 'app.beta',
                label: 'Beta',
                href: '/odoo/beta',
                webIconData: 'data:image/png;base64,AAAA',
            },
        ],
    });
    await mountWithCleanup(AppsBar);
    expect('.mk_apps_sidebar_menu .nav-link').toHaveCount(2);
    expect('.mk_apps_sidebar_icon').toHaveCount(2);
});

test.tags('muk_web_appsbar');
test('appsbar renders the company footer image when the company has one', async () => {
    patchActiveCompany({ has_appsbar_image: true, id: 7 });
    mockAppMenu();
    await mountWithCleanup(AppsBar);
    expect('.mk_apps_sidebar_logo').toHaveCount(1);
    expect('.mk_apps_sidebar_logo img').toHaveCount(1);
    expect('.mk_apps_sidebar_logo img').toHaveAttribute('alt', 'Logo');
});

test.tags('muk_web_appsbar');
test('appsbar omits the footer image when the company has none', async () => {
    patchActiveCompany({ has_appsbar_image: false });
    mockAppMenu();
    await mountWithCleanup(AppsBar);
    expect('.mk_apps_sidebar_logo').toHaveCount(0);
});

test.tags('muk_web_appsbar');
test('appsbar delegates a click on an app to the app_menu service', async () => {
    patchActiveCompany({ has_appsbar_image: false });
    const selected = [];
    mockAppMenu({ onSelectApp: (app) => selected.push(app) });
    await mountWithCleanup(AppsBar);
    await contains('.mk_apps_sidebar_menu .nav-link:first').click();
    expect(selected).toHaveLength(1);
    expect(selected[0].xmlid).toBe('app.alpha');
});

test.tags('muk_web_appsbar');
test('appsbar re-renders when the active app changes on the bus', async () => {
    patchActiveCompany({ has_appsbar_image: false });
    const state = mockAppMenu({ currentApp: { id: 1 } });
    await mountWithCleanup(AppsBar);
    expect('.nav-item.active .mk_apps_sidebar_name').toHaveText('Alpha');
    state.currentApp = { id: 2 };
    getMockEnv().bus.trigger('MENUS:APP-CHANGED');
    await animationFrame();
    expect('.nav-item.active .mk_apps_sidebar_name').toHaveText('Beta');
});
