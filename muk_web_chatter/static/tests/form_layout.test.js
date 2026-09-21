import { expect, test } from '@odoo/hoot';

import { session } from '@web/session';
import { SIZES } from '@web/core/ui/ui_utils';
import { FormRenderer } from '@web/views/form/form_renderer';
import { patchWithCleanup } from '@web/../tests/web_test_helpers';

import '@muk_web_chatter/views/form/form_renderer';

function makeRenderer({ xxl = true, hasFile = false, externalWindow = null } = {}) {
    return Object.assign(Object.create(FormRenderer.prototype), {
        uiService: { size: xxl ? SIZES.XXL : SIZES.LG },
        mailStore: {},
        mailPopoutService: { externalWindow },
        hasFile: () => hasFile,
    });
}

function layout(position, renderer, hasAttachmentContainer = false) {
    patchWithCleanup(session, { chatter_position: position });
    return renderer.mailLayout(hasAttachmentContainer);
}

test.tags('muk_web_chatter');
test('the side preference leaves every core layout alone', async () => {
    expect(layout('side', makeRenderer())).toBe('SIDE_CHATTER');
    expect(layout('side', makeRenderer({ xxl: false }))).toBe('BOTTOM_CHATTER');
    expect(layout('side', makeRenderer({ hasFile: true }), true)).toBe('COMBO');
    expect(
        layout('side', makeRenderer({ hasFile: true, externalWindow: {} }), true),
    ).toBe('EXTERNAL_COMBO_XXL');
});

test.tags('muk_web_chatter');
test('the bottom preference moves the side chatter below the sheet', async () => {
    expect(layout('bottom', makeRenderer())).toBe('BOTTOM_CHATTER');
});

test.tags('muk_web_chatter');
test('the bottom preference keeps the attachment preview', async () => {
    expect(layout('bottom', makeRenderer({ hasFile: true }), true)).toBe('COMBO');
    expect(
        layout('bottom', makeRenderer({ hasFile: true, externalWindow: {} }), true),
    ).toBe('EXTERNAL_COMBO');
});

test.tags('muk_web_chatter');
test('the bottom preference leaves a narrow window and an empty form alone', async () => {
    expect(layout('bottom', makeRenderer({ xxl: false }))).toBe('BOTTOM_CHATTER');
    const withoutChatter = makeRenderer();
    withoutChatter.mailStore = undefined;
    expect(layout('bottom', withoutChatter)).toBe('NONE');
});
