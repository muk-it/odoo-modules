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

function setTabHidden() {
    Object.defineProperty(document, 'hidden', {
        value: true,
        configurable: true,
        writable: true,
    });
    Object.defineProperty(document, 'visibilityState', {
        value: 'hidden',
        configurable: true,
        writable: true,
    });
    document.dispatchEvent(new Event('visibilitychange'));
}

function setTabVisible() {
    Object.defineProperty(document, 'hidden', {
        value: false,
        configurable: true,
        writable: true,
    });
    Object.defineProperty(document, 'visibilityState', {
        value: 'visible',
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

defineModels([Product]);
defineMailModels();

test.tags('muk_web_refresh', 'desktop');
test('refresh button is visible on list view', async () => {
    onRpc('has_group', () => true);
    await mountView({
        type: 'list',
        resModel: 'product',
        arch: `<list><field name="name"/></list>`,
    });
    expect('.mk_cp_refresh [data-icon="autorenew"]').toHaveCount(1);
});

test.tags('muk_web_refresh', 'desktop');
test('refresh button is visible on kanban view', async () => {
    onRpc('has_group', () => true);
    await mountView({
        type: 'kanban',
        resModel: 'product',
        arch: `
            <kanban>
                <templates>
                    <t t-name="card">
                        <field name="name"/>
                    </t>
                </templates>
            </kanban>
        `,
    });
    expect('.mk_cp_refresh [data-icon="autorenew"]').toHaveCount(1);
});

test.tags('muk_web_refresh', 'desktop');
test('refresh button is visible on form view', async () => {
    onRpc('has_group', () => true);
    await mountView({
        type: 'form',
        resModel: 'product',
        resId: 1,
        arch: `<form><field name="name"/></form>`,
    });
    expect('.mk_cp_refresh [data-icon="autorenew"]').toHaveCount(1);
});

test.tags('muk_web_refresh', 'desktop');
test('single click triggers refresh', async () => {
    onRpc('has_group', () => true);
    await mountView({
        type: 'list',
        resModel: 'product',
        arch: `<list><field name="name"/></list>`,
    });
    expect('.mk_cp_refresh [data-icon="autorenew"]').toHaveClass('text-muted');
    await click('.mk_cp_refresh [data-icon="autorenew"]');
    await advanceTime(350);
    expect('.mk_cp_refresh [data-icon="autorenew"]').toHaveClass('text-muted');
});

test.tags('muk_web_refresh', 'desktop');
test('double click toggles auto refresh on list view', async () => {
    onRpc('has_group', () => true);
    await mountView({
        type: 'list',
        resModel: 'product',
        arch: `<list><field name="name"/></list>`,
    });
    expect('.mk_cp_refresh [data-icon="autorenew"]').toHaveClass('text-muted');
    await dblclick('.mk_cp_refresh [data-icon="autorenew"]');
    await animationFrame();
    expect('.mk_cp_refresh [data-icon="autorenew"]').toHaveClass('text-info');
    expect('.mk_cp_refresh [data-icon="autorenew"]').not.toHaveClass('text-muted');
    await dblclick('.mk_cp_refresh [data-icon="autorenew"]');
    await animationFrame();
    expect('.mk_cp_refresh [data-icon="autorenew"]').not.toHaveClass('text-info');
    expect('.mk_cp_refresh [data-icon="autorenew"]').toHaveClass('text-muted');
});

test.tags('muk_web_refresh', 'desktop');
test('double click does not toggle auto refresh on form view', async () => {
    onRpc('has_group', () => true);
    await mountView({
        type: 'form',
        resModel: 'product',
        resId: 1,
        arch: `<form><field name="name"/></form>`,
    });
    expect('.mk_cp_refresh [data-icon="autorenew"]').toHaveClass('text-muted');
    await dblclick('.mk_cp_refresh [data-icon="autorenew"]');
    await animationFrame();
    expect('.mk_cp_refresh [data-icon="autorenew"]').toHaveClass('text-muted');
});

test.tags('muk_web_refresh', 'desktop');
test('auto-refresh pauses when tab is hidden', async () => {
    onRpc('has_group', () => true);
    let rpcCount = 0;
    onRpc('web_search_read', () => {
        rpcCount++;
    });
    await mountView({
        type: 'list',
        resModel: 'product',
        arch: `<list><field name="name"/></list>`,
    });
    await dblclick('.mk_cp_refresh [data-icon="autorenew"]');
    await animationFrame();
    expect('.mk_cp_refresh [data-icon="autorenew"]').toHaveClass('text-info');
    const countBefore = rpcCount;
    setTabHidden();
    await animationFrame();
    await advanceTime(35000);
    expect(rpcCount).toBe(countBefore);
    setTabVisible();
    await animationFrame();
    await advanceTime(35000);
    expect(rpcCount).toBeGreaterThan(countBefore);
});

test.tags('muk_web_refresh', 'desktop');
test('in-flight guard prevents overlapping refreshes', async () => {
    onRpc('has_group', () => true);
    const def = Promise.withResolvers();
    let refreshCount = 0;
    patchWithCleanup(ControlPanel.prototype, {
        refreshView() {
            refreshCount++;
            return def.promise;
        },
    });
    await mountView({
        type: 'list',
        resModel: 'product',
        arch: `<list><field name="name"/></list>`,
    });
    await dblclick('.mk_cp_refresh [data-icon="autorenew"]');
    await animationFrame();
    expect('.mk_cp_refresh [data-icon="autorenew"]').toHaveClass('text-info');
    await advanceTime(31000);
    expect(refreshCount).toBe(1);
    await advanceTime(31000);
    expect(refreshCount).toBe(1);
    def.resolve();
    await animationFrame();
    await advanceTime(31000);
    expect(refreshCount).toBe(2);
});

test.tags('muk_web_refresh', 'mobile');
test('a small screen shows no refresh button', async () => {
    onRpc('has_group', () => true);
    await mountView({
        type: 'list',
        resModel: 'product',
        arch: `<list><field name="name"/></list>`,
    });
    expect('.o_control_panel').toHaveCount(1);
    expect('.mk_cp_refresh').toHaveCount(0);
});
