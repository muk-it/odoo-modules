import { session } from '@web/session';
import { expect, test } from '@odoo/hoot';
import { animationFrame } from '@odoo/hoot-mock';

import { MainComponentsContainer } from '@web/core/main_components_container';
import { SelectCreateDialog } from '@web/views/view_dialogs/select_create_dialog';

import { defineMailModels } from '@mail/../tests/mail_test_helpers';
import {
    contains,
    defineModels,
    fields,
    getService,
    models,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
} from '@web/../tests/web_test_helpers';

import '@muk_web_dialog/core/dialog/dialog';

class MukDialogPartner extends models.Model {
    _name = 'muk.dialog.partner';
    name = fields.Char();
    _records = [{ id: 1, name: 'A' }];
    _views = {
        list: '<list><field name="name"/></list>',
        search: '<search/>',
    };
}

defineMailModels();
defineModels([MukDialogPartner]);

async function mountSelectCreateDialog(dialogSize) {
    patchWithCleanup(session, { dialog_size: dialogSize });
    onRpc('has_group', () => true);
    await mountWithCleanup(MainComponentsContainer);
    getService('dialog').add(SelectCreateDialog, { resModel: 'muk.dialog.partner' });
    await animationFrame();
}

test.tags('muk_web_dialog');
test('a dialog owning its header still gets the size toggle', async () => {
    await mountSelectCreateDialog('minimize');
    expect('.o_dialog .mk_btn_dialog_size').toHaveAttribute('data-icon', 'fullscreen');
    await contains('.o_dialog .mk_btn_dialog_size').click();
    expect('.o_dialog .modal-fs').toHaveCount(1);
    expect('.o_dialog .mk_btn_dialog_size').toHaveAttribute(
        'data-icon',
        'close_fullscreen',
    );
    await contains('.o_dialog .mk_btn_dialog_size').click();
    expect('.o_dialog .modal-fs').toHaveCount(0);
    expect('.o_dialog .mk_btn_dialog_size').toHaveAttribute('data-icon', 'fullscreen');
});

test.tags('muk_web_dialog');
test('a dialog owning its header honors the maximize preference', async () => {
    await mountSelectCreateDialog('maximize');
    expect('.o_dialog .modal-fs').toHaveCount(1);
    expect('.o_dialog .mk_btn_dialog_size').toHaveAttribute(
        'data-icon',
        'close_fullscreen',
    );
});
