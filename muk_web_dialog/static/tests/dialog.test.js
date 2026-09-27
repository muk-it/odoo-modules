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

test.tags('muk_web_dialog', 'desktop');
test('maximize preference opens the dialog fullscreen and the toggle restores it', async () => {
    await mountDialog('maximize');
    expect('.o_dialog .modal-fs').toHaveCount(1);
    expect('.o_dialog .mk_btn_dialog_size').toHaveAttribute(
        'data-icon',
        'close_fullscreen',
    );
    await contains('.o_dialog .mk_btn_dialog_size').click();
    expect('.o_dialog .modal-lg').toHaveCount(1);
    expect('.o_dialog .mk_btn_dialog_size').toHaveAttribute('data-icon', 'fullscreen');
});

test.tags('muk_web_dialog', 'desktop');
test('minimize preference keeps the requested size and the toggle returns to it', async () => {
    await mountDialog('minimize', 'xl');
    expect('.o_dialog .modal-xl').toHaveCount(1);
    await contains('.o_dialog .mk_btn_dialog_size').click();
    expect('.o_dialog .modal-fs').toHaveCount(1);
    await contains('.o_dialog .mk_btn_dialog_size').click();
    expect('.o_dialog .modal-xl').toHaveCount(1);
});

for (const size of ['sm', 'md']) {
    test.tags('muk_web_dialog', 'desktop');
    test(`a ${size} dialog ignores the maximize preference and offers no toggle`, async () => {
        await mountDialog('maximize', size);
        expect(`.o_dialog .modal-${size}`).toHaveCount(1);
        expect('.o_dialog .mk_btn_dialog_size').toHaveCount(0);
    });
}

test.tags('muk_web_dialog', 'mobile');
test('a small screen shows every dialog fullscreen without the size toggle', async () => {
    await mountDialog('maximize', 'xl');
    expect('.o_dialog .modal.o_modal_full').toHaveCount(1);
    expect('.o_dialog .mk_btn_dialog_size').toHaveCount(0);
});
