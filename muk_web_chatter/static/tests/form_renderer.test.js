import { describe, expect, test } from '@odoo/hoot';
import { animationFrame } from '@odoo/hoot-mock';
import { queryOne } from '@odoo/hoot-dom';

import { browser } from '@web/core/browser/browser';
import { session } from '@web/session';

import {
    SIZES,
    contains,
    defineMailModels,
    openFormView,
    patchUiSize,
    start,
    startServer,
} from '@mail/../tests/mail_test_helpers';
import { patchWithCleanup } from '@web/../tests/web_test_helpers';

describe.current.tags('desktop');
defineMailModels();

const ARCH = `
    <form string="Partners">
        <sheet>
            <field name="name"/>
        </sheet>
        <chatter/>
    </form>
`;

async function openPartnerForm() {
    patchUiSize({ size: SIZES.XXL });
    const pyEnv = await startServer();
    const partnerId = pyEnv['res.partner'].create({ name: 'Chatter Partner' });
    await start();
    await openFormView('res.partner', partnerId, { arch: ARCH });
    return partnerId;
}

function mouse(target, type, init = {}) {
    target.dispatchEvent(new MouseEvent(type, { button: 0, bubbles: true, ...init }));
}

function storedWidth() {
    return browser.localStorage.getItem('muk_web_chatter.width');
}

function chatterWidth() {
    return queryOne('.o-mail-Form-chatter').style.getPropertyValue(
        '--mk-Chatter-width',
    );
}

test.tags('muk_web_chatter');
test('the chatter position preference places the chatter', async () => {
    const partnerId = await openPartnerForm();
    await contains('.o-mail-Form-chatter.o-aside .mk_chatter_resize');
    patchWithCleanup(session, { chatter_position: 'bottom' });
    await openFormView('res.partner', partnerId, { arch: ARCH });
    await contains('.o-mail-Form-chatter:not(.o-aside)');
    await contains('.o-mail-Form-chatter.o-aside', { count: 0 });
});

test.tags('muk_web_chatter');
test('dragging the handle resizes the chatter within its bounds', async () => {
    await openPartnerForm();
    const chatter = queryOne('.o-mail-Form-chatter');
    const initialWidth = chatter.offsetWidth;
    const maxWidth = Math.max(chatter.parentElement.offsetWidth - 250, 250);
    mouse(queryOne('.mk_chatter_resize'), 'mousedown', { clientX: 600 });
    mouse(document, 'mousemove', { clientX: 500 });
    await animationFrame();
    expect(chatterWidth()).toBe(`${Math.min(initialWidth + 100, maxWidth)}px`);
    mouse(document, 'mousemove', { clientX: 100000 });
    await animationFrame();
    expect(chatterWidth()).toBe('50px');
    mouse(document, 'mouseup');
});

test.tags('muk_web_chatter');
test('releasing the handle stores the width and ends the drag', async () => {
    await openPartnerForm();
    mouse(queryOne('.mk_chatter_resize'), 'mousedown', { clientX: 600 });
    mouse(document, 'mousemove', { clientX: 500 });
    await animationFrame();
    const width = chatterWidth();
    expect(storedWidth()).toBe(null);
    mouse(document, 'mouseup');
    mouse(document, 'mousemove', { clientX: 200 });
    await animationFrame();
    expect(storedWidth()).toBe(width.replace('px', ''));
    expect(chatterWidth()).toBe(width);
});

test.tags('muk_web_chatter');
test('a non primary mouse button does not start a resize', async () => {
    await openPartnerForm();
    mouse(queryOne('.mk_chatter_resize'), 'mousedown', { button: 2, clientX: 600 });
    mouse(document, 'mousemove', { clientX: 400 });
    await animationFrame();
    expect(chatterWidth()).toBe('');
});

test.tags('muk_web_chatter');
test('a stored width is restored and double clicking the handle resets it', async () => {
    browser.localStorage.setItem('muk_web_chatter.width', '640');
    await openPartnerForm();
    expect(chatterWidth()).toBe('640px');
    mouse(queryOne('.mk_chatter_resize'), 'dblclick');
    await animationFrame();
    expect(storedWidth()).toBe(null);
    expect(chatterWidth()).toBe('');
});
