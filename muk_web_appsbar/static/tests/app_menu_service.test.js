import { user } from '@web/core/user';
import { expect, test } from '@odoo/hoot';
import { patchWithCleanup } from '@web/../tests/web_test_helpers';

import { makeMenuTree, startAppMenuService } from './helpers/app_menu';

function patchHomeMenuConfig(homemenu_config) {
    const realSettings = user.settings;
    patchWithCleanup(user, {
        get settings() {
            return { ...realSettings, homemenu_config };
        },
    });
}

const THREE_APPS = [
    { id: 1, name: 'Alpha', xmlid: 'app.alpha', actionID: 11 },
    { id: 2, name: 'Beta', xmlid: 'app.beta', actionID: 12 },
    { id: 3, name: 'Gamma', xmlid: 'app.gamma', actionID: 13 },
];

test.tags('muk_web_appsbar');
test('app_menu service reorders apps based on the stored homemenu config', async () => {
    patchHomeMenuConfig(JSON.stringify(['app.gamma', 'app.alpha', 'app.beta']));
    const service = await startAppMenuService({ tree: makeMenuTree(THREE_APPS) });
    expect(service.getAppsMenuItems().map((app) => app.xmlid)).toEqual([
        'app.gamma',
        'app.alpha',
        'app.beta',
    ]);
});

test.tags('muk_web_appsbar');
test('app_menu service keeps the menu order when no homemenu config is stored', async () => {
    patchHomeMenuConfig(false);
    const service = await startAppMenuService({ tree: makeMenuTree(THREE_APPS) });
    expect(service.getAppsMenuItems().map((app) => app.xmlid)).toEqual([
        'app.alpha',
        'app.beta',
        'app.gamma',
    ]);
});

test.tags('muk_web_appsbar');
test('app_menu service puts apps missing from the config first', async () => {
    patchHomeMenuConfig(JSON.stringify(['app.beta']));
    const service = await startAppMenuService({ tree: makeMenuTree(THREE_APPS) });
    expect(service.getAppsMenuItems().map((app) => app.xmlid)).toEqual([
        'app.alpha',
        'app.gamma',
        'app.beta',
    ]);
});

test.tags('muk_web_appsbar');
test('app_menu service exposes only apps, not their sub menu items', async () => {
    patchHomeMenuConfig(false);
    const tree = makeMenuTree([THREE_APPS[0]]);
    tree.childrenTree[0].childrenTree.push({
        id: 100,
        appID: 1,
        name: 'Alpha Child',
        xmlid: 'app.alpha.child',
        actionID: 111,
        childrenTree: [],
    });
    const service = await startAppMenuService({ tree });
    const apps = service.getAppsMenuItems();
    expect(apps).toHaveLength(1);
    expect(apps[0].xmlid).toBe('app.alpha');
    expect(apps[0].href).toBe('/odoo/action-11');
});

test.tags('muk_web_appsbar');
test('app_menu service delegates selectApp and getCurrentApp to the menu service', async () => {
    patchHomeMenuConfig(false);
    const selected = [];
    const currentApp = { id: 2, xmlid: 'app.beta' };
    const service = await startAppMenuService({
        tree: makeMenuTree(THREE_APPS),
        currentApp,
        onSelectMenu: (app) => selected.push(app),
    });
    expect(service.getCurrentApp()).toBe(currentApp);
    service.selectApp(service.getAppsMenuItems()[0]);
    expect(selected).toHaveLength(1);
    expect(selected[0].xmlid).toBe('app.alpha');
});
