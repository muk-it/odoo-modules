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

test.tags('muk_web_chatter');
test('dragging the handle to the left widens the chatter and persists the width', async () => {
    await openPartnerForm();
    const chatter = queryOne('.o_form_renderer > .o-mail-Form-chatter');
    const initialWidth = chatter.offsetWidth;
    const maxWidth = Math.max(chatter.parentElement.offsetWidth - 250, 250);
    startDrag(600);
    moveTo(500);
    await animationFrame();
    const storedWidth = Number(browser.localStorage.getItem('muk_web_chatter.width'));
    expect(storedWidth).toBe(Math.min(initialWidth + 100, maxWidth));
    expect(chatter.style.width).toBe(`${storedWidth}px`);
    expect(chatter.style.maxWidth).toBe(`${storedWidth}px`);
    stopDrag();
});

test.tags('muk_web_chatter');
test('dragging never shrinks the chatter below its minimum width', async () => {
    await openPartnerForm();
    startDrag(600);
    moveTo(100000);
    await animationFrame();
    expect(Number(browser.localStorage.getItem('muk_web_chatter.width'))).toBe(50);
    stopDrag();
});

test.tags('muk_web_chatter');
test('dragging stops tracking the mouse after the button is released', async () => {
    await openPartnerForm();
    startDrag(600);
    moveTo(500);
    await animationFrame();
    const widthAfterDrag = browser.localStorage.getItem('muk_web_chatter.width');
    stopDrag();
    moveTo(200);
    await animationFrame();
    expect(browser.localStorage.getItem('muk_web_chatter.width')).toBe(widthAfterDrag);
});

test.tags('muk_web_chatter');
test('a non primary mouse button does not start a resize', async () => {
    await openPartnerForm();
    queryOne('.mk_chatter_resize').dispatchEvent(
        new MouseEvent('mousedown', { button: 2, clientX: 600, bubbles: true }),
    );
    moveTo(400);
    await animationFrame();
    expect(browser.localStorage.getItem('muk_web_chatter.width')).toBe(null);
});

test.tags('muk_web_chatter');
test('double clicking the handle clears the stored width', async () => {
    await openPartnerForm();
    startDrag(600);
    moveTo(500);
    await animationFrame();
    stopDrag();
    expect(browser.localStorage.getItem('muk_web_chatter.width')).not.toBe(null);
    queryOne('.mk_chatter_resize').dispatchEvent(
        new MouseEvent('dblclick', { bubbles: true }),
    );
    await animationFrame();
    expect(browser.localStorage.getItem('muk_web_chatter.width')).toBe(null);
    expect(queryOne('.o_form_renderer > .o-mail-Form-chatter').style.width).toBe('');
});

test.tags('muk_web_chatter');
test('a stored width is restored on the next form render', async () => {
    browser.localStorage.setItem('muk_web_chatter.width', '321');
    await openPartnerForm();
    expect(queryOne('.o_form_renderer > .o-mail-Form-chatter').style.width).toBe(
        '321px',
    );
});
