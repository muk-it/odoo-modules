import { expect, test } from '@odoo/hoot';
import { click, dblclick } from '@odoo/hoot-dom';
import { advanceTime, animationFrame } from '@odoo/hoot-mock';

import { ControlPanel } from '@web/search/control_panel/control_panel';
import {
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
    patchWithCleanup,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import '@muk_web_refresh/search/control_panel/control_panel';

const BUTTON = '.mk_cp_refresh [data-icon="autorenew"]';
const LIST = {
    type: 'list',
    resModel: 'product',
    arch: '<list><field name="name"/></list>',
};
const FORM = {
    type: 'form',
    resModel: 'product',
    resId: 1,
    arch: '<form><field name="name"/></form>',
};

function setTabHidden(hidden) {
    Object.defineProperty(document, 'hidden', {
        value: hidden,
        configurable: true,
        writable: true,
    });
    document.dispatchEvent(new Event('visibilitychange'));
}

class Product extends models.Model {
    _records = [
        { id: 1, name: 'Test 1' },
        { id: 2, name: 'Test 2' },
    ];
    name = fields.Char();
}

class ResConfigSettings extends models.Model {
    _name = 'res.config.settings';
    bar = fields.Boolean();
}

defineModels([Product, ResConfigSettings]);
defineMailModels();

test.tags('muk_web_refresh', 'desktop');
test('a single click reloads the list and flashes the content', async () => {
    onRpc('web_search_read', () => expect.step('reload'));
    await mountView(LIST);
    expect.verifySteps(['reload']);
    await click(BUTTON);
    await advanceTime(350);
    expect.verifySteps(['reload']);
    expect('.o_content').toHaveClass('mk_refresh');
    await advanceTime(600);
    expect('.o_content').not.toHaveClass('mk_refresh');
});

test.tags('muk_web_refresh', 'desktop');
test('a double click toggles auto refresh with a countdown instead of reloading', async () => {
    onRpc('web_search_read', () => expect.step('reload'));
    await mountView(LIST);
    expect.verifySteps(['reload']);
    expect(BUTTON).toHaveClass('text-muted');
    await dblclick(BUTTON);
    await advanceTime(350);
    expect(BUTTON).toHaveClass('text-info');
    expect('.mk_cp_refresh .small').toHaveText('30s');
    await advanceTime(1000);
    expect('.mk_cp_refresh .small').toHaveText('29s');
    expect.verifySteps([]);
    await dblclick(BUTTON);
    await animationFrame();
    expect(BUTTON).toHaveClass('text-muted');
    expect('.mk_cp_refresh .small').toHaveCount(0);
});

test.tags('muk_web_refresh', 'desktop');
test('auto refresh stays on for the next visit of the same view', async () => {
    await mountView(LIST);
    await dblclick(BUTTON);
    await animationFrame();
    await mountView(LIST);
    expect('.mk_cp_refresh .text-info').toHaveCount(2);
});

test.tags('muk_web_refresh', 'desktop');
test('a double click on a form view does not turn on auto refresh', async () => {
    await mountView(FORM);
    expect(BUTTON).toHaveClass('text-muted');
    await dblclick(BUTTON);
    await animationFrame();
    expect(BUTTON).toHaveClass('text-muted');
});

test.tags('muk_web_refresh', 'desktop');
test('the settings form has no refresh button', async () => {
    onRpc('/base_setup/demo_active', () => true);
    await mountView({
        type: 'form',
        resModel: 'res.config.settings',
        arch: `
            <form js_class="base_settings">
                <app string="App" name="app">
                    <setting><field name="bar"/></setting>
                </app>
            </form>
        `,
    });
    expect('.o_control_panel').toHaveCount(1);
    expect('.mk_cp_refresh').toHaveCount(0);
});

test.tags('muk_web_refresh', 'desktop');
test('auto refresh pauses while the tab is hidden', async () => {
    onRpc('web_search_read', () => expect.step('reload'));
    await mountView(LIST);
    await dblclick(BUTTON);
    await animationFrame();
    expect.verifySteps(['reload']);
    setTabHidden(true);
    await animationFrame();
    await advanceTime(35000);
    expect.verifySteps([]);
    setTabHidden(false);
    await animationFrame();
    await advanceTime(31000);
    expect.verifySteps(['reload']);
});

test.tags('muk_web_refresh', 'desktop');
test('auto refresh waits for a slow reload before starting the next one', async () => {
    const reload = Promise.withResolvers();
    patchWithCleanup(ControlPanel.prototype, {
        refreshView() {
            expect.step('reload');
            return reload.promise;
        },
    });
    await mountView(LIST);
    await dblclick(BUTTON);
    await animationFrame();
    await advanceTime(31000);
    expect.verifySteps(['reload']);
    await advanceTime(31000);
    expect.verifySteps([]);
    reload.resolve();
    await animationFrame();
    await advanceTime(31000);
    expect.verifySteps(['reload']);
});

test.tags('muk_web_refresh', 'mobile');
test('a small screen shows no refresh button', async () => {
    await mountView(LIST);
    expect('.o_control_panel').toHaveCount(1);
    expect('.mk_cp_refresh').toHaveCount(0);
});
