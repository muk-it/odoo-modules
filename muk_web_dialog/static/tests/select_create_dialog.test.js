import { expect, test } from '@odoo/hoot';

import { SelectCreateDialog } from '@web/views/view_dialogs/select_create_dialog';

import '@muk_web_dialog/views/view_dialogs/select_create_dialog';

function makeSelectCreateDialog(dialogData) {
    return Object.assign(Object.create(SelectCreateDialog.prototype), {
        env: { dialogData },
    });
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
