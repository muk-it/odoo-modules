import { describe, expect, test } from '@odoo/hoot';
import { session } from '@web/session';

import {
    contains,
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

function makeArch(field) {
    return `
        <form string="Partners">
            <sheet>
                <field name="${field}"/>
            </sheet>
            <chatter/>
        </form>
    `;
}

async function openPartnerForm(chatterPosition, arch) {
    patchWithCleanup(session, { chatter_position: chatterPosition });
    const pyEnv = await startServer();
    const partnerId = pyEnv['res.partner'].create({ name: 'Chatter Partner' });
    await start();
    await openFormView('res.partner', partnerId, { arch });
}

test.tags('muk_web_chatter');
test('side chatter position keeps the chatter aside with a resize handle', async () => {
    await openPartnerForm('side', makeArch('name'));
    await contains('.o-mail-Chatter');
    expect('.mk_chatter_resize').toHaveCount(1);
    expect('.o_form_sheet_bg .o-mail-Form-chatter').toHaveCount(0);
});

test.tags('muk_web_chatter');
test('bottom chatter position moves the chatter into the form sheet', async () => {
    await openPartnerForm('bottom', makeArch('email'));
    await contains('.o_form_sheet_bg .o-mail-Form-chatter.o-isInFormSheetBg');
    await contains('.o-mail-Chatter');
    expect('.mk_chatter_resize').toHaveCount(0);
});

test.tags('muk_web_chatter');
test('unset chatter position falls back to the aside layout', async () => {
    await openPartnerForm(undefined, makeArch('phone'));
    await contains('.o-mail-Chatter');
    expect('.mk_chatter_resize').toHaveCount(1);
    expect('.o_form_sheet_bg .o-mail-Form-chatter').toHaveCount(0);
});

test.tags('muk_web_chatter');
test('form without a chatter is left untouched', async () => {
    await openPartnerForm('side', '<form><sheet><field name="name"/></sheet></form>');
    await contains('.o_form_sheet_bg');
    expect('.o-mail-Chatter').toHaveCount(0);
    expect('.mk_chatter_resize').toHaveCount(0);
});
