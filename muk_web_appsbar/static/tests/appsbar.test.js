import { animationFrame, beforeEach, describe, expect, test } from '@odoo/hoot';
import { queryAllAttributes, queryAllTexts, queryOne } from '@odoo/hoot-dom';

import { user } from '@web/core/user';
import {
    contains,
    defineActions,
    defineMenus,
    mountWebClient,
    patchWithCleanup,
    useTestClientAction,
} from '@web/../tests/web_test_helpers';

describe.current.tags('desktop');

function patchActiveCompany(values) {
    const company = { ...user.activeCompany, ...values };
    patchWithCleanup(user, {
        get activeCompany() {
            return company;
        },
    });
}

beforeEach(() => {
    const clientAction = useTestClientAction();
    defineActions([
        { ...clientAction, id: 11, params: { description: 'Alpha' } },
        { ...clientAction, id: 12, params: { description: 'Beta' } },
    ]);
    defineMenus([
        {
            id: 1,
            name: 'Alpha',
            xmlid: 'app.alpha',
            actionID: 11,
            webIconData: 'data:image/png;base64,AAAA',
        },
        {
            id: 2,
            name: 'Beta',
            xmlid: 'app.beta',
            actionID: 12,
            webIcon: 'fa-b,#fff,#000',
        },
    ]);
    patchActiveCompany({ has_appsbar_image: false });
});

test.tags('muk_web_appsbar');
test('web client renders the installed apps in the sidebar', async () => {
    await mountWebClient();
    expect('.o_web_client > .mk_apps_sidebar_panel').toHaveCount(1);
    expect(queryAllTexts('.mk_apps_sidebar_name')).toEqual(['Alpha', 'Beta']);
    expect(queryAllAttributes('.mk_apps_sidebar_menu .nav-link', 'href')).toEqual([
        '/odoo/action-11',
        '/odoo/action-12',
    ]);
    expect(queryAllAttributes('.mk_apps_sidebar_icon', 'data-src')).toEqual([
        'data:image/png;base64,AAAA',
        '/base/static/description/icon.png',
    ]);
    expect('.mk_apps_sidebar_logo').toHaveCount(0);
});

test.tags('muk_web_appsbar');
test('clicking an app opens its action and marks it active', async () => {
    await mountWebClient();
    expect('.test_client_action').toHaveText('ClientAction_Alpha');
    expect('.nav-item.active').toHaveText('Alpha');
    await contains('.mk_apps_sidebar_menu .nav-link:contains(Beta)').click();
    await animationFrame();
    expect('.test_client_action').toHaveText('ClientAction_Beta');
    expect('.nav-item.active').toHaveText('Beta');
});

test.tags('muk_web_appsbar');
test('sidebar follows the home menu order stored in the user settings', async () => {
    const settings = user.settings;
    patchWithCleanup(user, {
        get settings() {
            return { ...settings, homemenu_config: '["app.beta", "app.alpha"]' };
        },
    });
    await mountWebClient();
    expect(queryAllTexts('.mk_apps_sidebar_name')).toEqual(['Beta', 'Alpha']);
});

test.tags('muk_web_appsbar');
test('sidebar shows the image of the active company', async () => {
    patchActiveCompany({ id: 7, has_appsbar_image: true });
    await mountWebClient();
    expect(queryOne('.mk_apps_sidebar_logo img').dataset.src).toInclude(
        '/web/image?model=res.company&field=appbar_image&id=7',
    );
});
