import { expect, test } from '@odoo/hoot';
import { animationFrame } from '@odoo/hoot-mock';

import { MainComponentsContainer } from '@web/core/main_components_container';
import { SelectCreateDialog } from '@web/views/view_dialogs/select_create_dialog';

import {
    contains,
    defineModels,
    fields,
    getService,
    models,
    mountWithCleanup,
    onRpc,
} from '@web/../tests/web_test_helpers';

import '@muk_web_dialog/core/dialog/dialog';
import '@muk_web_dialog/views/view_dialogs/select_create_dialog';

class MukDialogPartner extends models.Model {
    _name = 'muk.dialog.partner';

    name = fields.Char();

    _records = [{ id: 1, name: 'A' }];
    _views = {
        list: '<list><field name="name"/></list>',
        search: '<search/>',
    };
}

defineModels([MukDialogPartner]);

/**
 * Build a select create dialog bound to the given dialog data.
 *
 * @param {Object} dialogData the reactive dialog data of the dialog service
 * @returns {SelectCreateDialog} a dialog instance ready to be toggled
 */
function makeSelectCreateDialog(dialogData) {
    return Object.assign(Object.create(SelectCreateDialog.prototype), {
        env: { dialogData },
    });
}

/**
 * Open a select create dialog on the test model.
 *
 * @returns {Promise<void>} resolved once the dialog is rendered
 */
async function mountSelectCreateDialog() {
    onRpc('has_group', () => true);
    await mountWithCleanup(MainComponentsContainer);
    getService('dialog').add(SelectCreateDialog, { resModel: 'muk.dialog.partner' });
    await animationFrame();
}

test.tags('muk_web_dialog');
test('select create dialog grows to fullscreen and back to its initial size', async () => {
    const dialogData = { size: 'lg', initalSize: 'lg' };
    const dialog = makeSelectCreateDialog(dialogData);
    dialog.onClickDialogSizeToggle();
    expect(dialogData.size).toBe('fs');
    dialog.onClickDialogSizeToggle();
    expect(dialogData.size).toBe('lg');
});

test.tags('muk_web_dialog');
test('select create dialog opened fullscreen shrinks to its initial size', async () => {
    const dialogData = { size: 'fs', initalSize: 'md' };
    const dialog = makeSelectCreateDialog(dialogData);
    dialog.onClickDialogSizeToggle();
    expect(dialogData.size).toBe('md');
    dialog.onClickDialogSizeToggle();
    expect(dialogData.size).toBe('fs');
});

test.tags('muk_web_dialog');
test('the select create dialog size toggle reflects the fullscreen state', async () => {
    await mountSelectCreateDialog();
    expect('.o_dialog .mk_btn_dialog_size').toHaveCount(1);
    expect('.o_dialog .mk_btn_dialog_size i.fa-expand').toHaveCount(1);
    await contains('.o_dialog .mk_btn_dialog_size').click();
    expect('.o_dialog .modal-fs').toHaveCount(1);
    expect('.o_dialog .mk_btn_dialog_size i.fa-compress').toHaveCount(1);
    await contains('.o_dialog .mk_btn_dialog_size').click();
    expect('.o_dialog .modal-fs').toHaveCount(0);
    expect('.o_dialog .mk_btn_dialog_size i.fa-expand').toHaveCount(1);
});
