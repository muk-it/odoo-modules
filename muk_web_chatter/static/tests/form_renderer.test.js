import { describe, expect, test } from '@odoo/hoot';
import { animationFrame } from '@odoo/hoot-mock';
import { queryOne } from '@odoo/hoot-dom';

import { browser } from '@web/core/browser/browser';
import { session } from '@web/session';

import {
    defineMailModels,
    openFormView,
    start,
    startServer,
} from '@mail/../tests/mail_test_helpers';
import { patchWithCleanup } from '@web/../tests/web_test_helpers';

import '@muk_web_chatter/views/form/form_compiler';
import '@muk_web_chatter/views/form/form_renderer';

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
    patchWithCleanup(session, { chatter_position: 'side' });
    const pyEnv = await startServer();
    const partnerId = pyEnv['res.partner'].create({ name: 'Chatter Partner' });
    await start();
    await openFormView('res.partner', partnerId, { arch: ARCH });
}

function startDrag(fromX) {
    queryOne('.mk_chatter_resize').dispatchEvent(
        new MouseEvent('mousedown', { button: 0, clientX: fromX, bubbles: true }),
    );
}

function moveTo(toX) {
    document.dispatchEvent(
        new MouseEvent('mousemove', { clientX: toX, bubbles: true }),
    );
}

function stopDrag() {
    document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
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
test('dragging the handle to the left widens the chatter', async () => {
    await openPartnerForm();
    const chatter = queryOne('.o-mail-Form-chatter');
    const initialWidth = chatter.offsetWidth;
    const maxWidth = Math.max(chatter.parentElement.offsetWidth - 250, 250);
    startDrag(600);
    moveTo(500);
    await animationFrame();
    expect(chatterWidth()).toBe(`${Math.min(initialWidth + 100, maxWidth)}px`);
    stopDrag();
});

test.tags('muk_web_chatter');
test('the width reaches local storage when the drag ends, not while it runs', async () => {
    await openPartnerForm();
    startDrag(600);
    moveTo(500);
    await animationFrame();
    expect(storedWidth()).toBe(null);
    stopDrag();
    await animationFrame();
    expect(storedWidth()).toBe(chatterWidth().replace('px', ''));
});

test.tags('muk_web_chatter');
test('dragging never shrinks the chatter below its minimum width', async () => {
    await openPartnerForm();
    startDrag(600);
    moveTo(100000);
    await animationFrame();
    expect(chatterWidth()).toBe('50px');
    stopDrag();
});

test.tags('muk_web_chatter');
test('dragging stops tracking the mouse after the button is released', async () => {
    await openPartnerForm();
    startDrag(600);
    moveTo(500);
    await animationFrame();
    const widthAfterDrag = chatterWidth();
    stopDrag();
    moveTo(200);
    await animationFrame();
    expect(chatterWidth()).toBe(widthAfterDrag);
});

test.tags('muk_web_chatter');
test('a non primary mouse button does not start a resize', async () => {
    await openPartnerForm();
    queryOne('.mk_chatter_resize').dispatchEvent(
        new MouseEvent('mousedown', { button: 2, clientX: 600, bubbles: true }),
    );
    moveTo(400);
    await animationFrame();
    expect(chatterWidth()).toBe('');
});

test.tags('muk_web_chatter');
test('double clicking the handle clears the stored width', async () => {
    await openPartnerForm();
    startDrag(600);
    moveTo(500);
    stopDrag();
    await animationFrame();
    expect(storedWidth()).not.toBe(null);
    queryOne('.mk_chatter_resize').dispatchEvent(
        new MouseEvent('dblclick', { bubbles: true }),
    );
    await animationFrame();
    expect(storedWidth()).toBe(null);
    expect(chatterWidth()).toBe('');
});

test.tags('muk_web_chatter');
test('a stored width is restored on the next form render', async () => {
    browser.localStorage.setItem('muk_web_chatter.width', '640');
    await openPartnerForm();
    expect(chatterWidth()).toBe('640px');
});
