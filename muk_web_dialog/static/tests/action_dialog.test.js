import { expect, test } from '@odoo/hoot';

import { Component, xml } from '@odoo/owl';
import { ActionDialog } from '@web/webclient/actions/action_dialog';

import { defineMailModels } from '@mail/../tests/mail_test_helpers';
import {
    assignDialogTestEnv,
    contains,
    mountWithCleanup,
} from '@web/../tests/web_test_helpers';

import '@muk_web_dialog/core/dialog/dialog';
import '@muk_web_dialog/webclient/actions/action_dialog';

defineMailModels();

async function mountComposerDialog() {
    class Parent extends Component {
        static components = { ActionDialog };
        static template = xml`
            <ActionDialog
                title="'Compose Email'"
                actionProps="{ resModel: 'mail.compose.message', type: 'form' }"
            />
        `;
    }

    assignDialogTestEnv();
    await mountWithCleanup(Parent);
}

test.tags('muk_web_dialog');
test('the composer dialog carries a single size toggle', async () => {
    await mountComposerDialog();
    expect('.o_dialog .modal-header button[data-icon]').toHaveCount(1);
    expect('.o_dialog .mk_btn_dialog_size').toHaveAttribute('data-icon', 'fullscreen');
});

test.tags('muk_web_dialog');
test('the composer dialog size toggle drives the dialog size', async () => {
    await mountComposerDialog();
    expect('.o_dialog .modal-fs').toHaveCount(0);
    await contains('.o_dialog .mk_btn_dialog_size').click();
    expect('.o_dialog .modal-fs').toHaveCount(1);
    expect('.o_dialog .mk_btn_dialog_size').toHaveAttribute(
        'data-icon',
        'close_fullscreen',
    );
});
