import { session } from '@web/session';
import { expect, test } from '@odoo/hoot';

import { Component, xml } from '@odoo/owl';
import { Dialog } from '@web/core/dialog/dialog';

import {
    contains,
    makeDialogMockEnv,
    mountWithCleanup,
    patchWithCleanup,
} from '@web/../tests/web_test_helpers';

import '@muk_web_dialog/core/dialog/dialog';

async function mountDialog(dialogSize, size) {
    patchWithCleanup(session, { dialog_size: dialogSize });

    class Parent extends Component {
        static components = { Dialog };
        static template = size
            ? xml`<Dialog title="'Hello'" size="'${size}'">Hello</Dialog>`
            : xml`<Dialog title="'Hello'">Hello</Dialog>`;
        static props = ['*'];
    }

    await makeDialogMockEnv();
    await mountWithCleanup(Parent);
}

test.tags('muk_web_dialog');
test('maximize preference opens the dialog fullscreen', async () => {
    await mountDialog('maximize');
    expect('.o_dialog .modal-fs').toHaveCount(1);
    expect('.o_dialog .mk_btn_dialog_size i.fa-compress').toHaveCount(1);
});

test.tags('muk_web_dialog');
test('minimize preference keeps the requested dialog size', async () => {
    await mountDialog('minimize');
    expect('.o_dialog .modal-lg').toHaveCount(1);
    expect('.o_dialog .modal-fs').toHaveCount(0);
    expect('.o_dialog .mk_btn_dialog_size i.fa-expand').toHaveCount(1);
});

test.tags('muk_web_dialog');
test('an unset preference keeps the requested dialog size', async () => {
    await mountDialog(undefined, 'md');
    expect('.o_dialog .modal-md').toHaveCount(1);
    expect('.o_dialog .mk_btn_dialog_size i.fa-expand').toHaveCount(1);
});

test.tags('muk_web_dialog');
test('the size toggle switches back to the size the dialog was opened with', async () => {
    await mountDialog('minimize', 'sm');
    expect('.o_dialog .modal-sm').toHaveCount(1);
    await contains('.o_dialog .mk_btn_dialog_size').click();
    expect('.o_dialog .modal-fs').toHaveCount(1);
    expect('.o_dialog .mk_btn_dialog_size i.fa-compress').toHaveCount(1);
    await contains('.o_dialog .mk_btn_dialog_size').click();
    expect('.o_dialog .modal-sm').toHaveCount(1);
    expect('.o_dialog .mk_btn_dialog_size i.fa-expand').toHaveCount(1);
});

test.tags('muk_web_dialog');
test('the size toggle restores the default size for a maximized dialog', async () => {
    await mountDialog('maximize');
    expect('.o_dialog .modal-fs').toHaveCount(1);
    await contains('.o_dialog .mk_btn_dialog_size').click();
    expect('.o_dialog .modal-lg').toHaveCount(1);
    await contains('.o_dialog .mk_btn_dialog_size').click();
    expect('.o_dialog .modal-fs').toHaveCount(1);
});

test.tags('muk_web_dialog');
test('the dialog title leaves room for the size toggle', async () => {
    await mountDialog('minimize');
    expect('.o_dialog .modal-title').toHaveClass('w-75');
    expect('.o_dialog .mk_btn_dialog_size').toHaveCount(1);
});
