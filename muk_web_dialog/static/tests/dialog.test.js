import { session } from '@web/session';
import { expect, test } from '@odoo/hoot';

import { Component, xml } from '@odoo/owl';
import { Dialog } from '@web/core/dialog/dialog';

import { defineMailModels } from '@mail/../tests/mail_test_helpers';
import {
    assignDialogTestEnv,
    contains,
    mountWithCleanup,
    patchWithCleanup,
} from '@web/../tests/web_test_helpers';

import '@muk_web_dialog/core/dialog/dialog';

defineMailModels();

async function mountDialog(dialogSize, size) {
    patchWithCleanup(session, { dialog_size: dialogSize });

    class Parent extends Component {
        static components = { Dialog };
        static template = size
            ? xml`<Dialog title="'Hello'" size="'${size}'">Hello</Dialog>`
            : xml`<Dialog title="'Hello'">Hello</Dialog>`;
    }

    assignDialogTestEnv();
    await mountWithCleanup(Parent);
}

test.tags('muk_web_dialog');
test('maximize preference opens the dialog fullscreen', async () => {
    await mountDialog('maximize');
    expect('.o_dialog .modal-fs').toHaveCount(1);
    expect('.o_dialog .mk_btn_dialog_size').toHaveAttribute(
        'data-icon',
        'close_fullscreen',
    );
});

test.tags('muk_web_dialog');
test('minimize preference keeps the requested dialog size', async () => {
    await mountDialog('minimize');
    expect('.o_dialog .modal-lg').toHaveCount(1);
    expect('.o_dialog .modal-fs').toHaveCount(0);
    expect('.o_dialog .mk_btn_dialog_size').toHaveAttribute('data-icon', 'fullscreen');
});

test.tags('muk_web_dialog');
test('an unset preference keeps the requested dialog size', async () => {
    await mountDialog(undefined, 'xl');
    expect('.o_dialog .modal-xl').toHaveCount(1);
    expect('.o_dialog .mk_btn_dialog_size').toHaveAttribute('data-icon', 'fullscreen');
});

test.tags('muk_web_dialog');
test('the size toggle switches back to the size the dialog was opened with', async () => {
    await mountDialog('minimize', 'xl');
    expect('.o_dialog .modal-xl').toHaveCount(1);
    await contains('.o_dialog .mk_btn_dialog_size').click();
    expect('.o_dialog .modal-fs').toHaveCount(1);
    expect('.o_dialog .mk_btn_dialog_size').toHaveAttribute(
        'data-icon',
        'close_fullscreen',
    );
    await contains('.o_dialog .mk_btn_dialog_size').click();
    expect('.o_dialog .modal-xl').toHaveCount(1);
    expect('.o_dialog .mk_btn_dialog_size').toHaveAttribute('data-icon', 'fullscreen');
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
test('a small dialog is left minimal and offers no size toggle', async () => {
    await mountDialog('maximize', 'sm');
    expect('.o_dialog .modal-sm').toHaveCount(1);
    expect('.o_dialog .modal-fs').toHaveCount(0);
    expect('.o_dialog .mk_btn_dialog_size').toHaveCount(0);
});

test.tags('muk_web_dialog');
test('a medium dialog is left minimal and offers no size toggle', async () => {
    await mountDialog('maximize', 'md');
    expect('.o_dialog .modal-md').toHaveCount(1);
    expect('.o_dialog .mk_btn_dialog_size').toHaveCount(0);
});

test.tags('muk_web_dialog');
test('the expand button keeps pointing at the form view', async () => {
    patchWithCleanup(session, { dialog_size: 'minimize' });

    class Parent extends Component {
        static components = { Dialog };
        static template = xml`<Dialog title="'Hello'" onExpand="this.onExpand">Hello</Dialog>`;
        onExpand() {}
    }

    assignDialogTestEnv();
    await mountWithCleanup(Parent);
    expect('.o_dialog .o_expand_button').toHaveAttribute('data-icon', 'open_in_new');
    expect('.o_dialog .mk_btn_dialog_size').toHaveAttribute('data-icon', 'fullscreen');
});
