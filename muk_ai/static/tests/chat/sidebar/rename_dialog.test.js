import { describe, expect, test } from '@odoo/hoot';
import { press } from '@odoo/hoot-dom';
import { tick } from '@odoo/hoot-mock';
import {
    contains,
    makeDialogMockEnv,
    mountWithCleanup,
    patchTranslations,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { RenameDialog } from '@muk_ai/chat/sidebar/rename_dialog';

describe.current.tags('muk_ai');
defineMailModels();
patchTranslations();

test('RenameDialog focuses the input pre-filled with initial value', async () => {
    const env = await makeDialogMockEnv();
    await mountWithCleanup(RenameDialog, {
        env,
        props: {
            close: () => {},
            initial: 'Old Chat',
            onConfirm: () => {},
        },
    });
    const input = document.querySelector('input');
    expect(input).not.toBe(null);
    expect(input.value).toBe('Old Chat');
});

test('RenameDialog confirms trimmed value and closes on Enter', async () => {
    const env = await makeDialogMockEnv();
    let received = null;
    let closed = false;
    await mountWithCleanup(RenameDialog, {
        env,
        props: {
            close: () => {
                closed = true;
            },
            initial: 'Old',
            onConfirm: (v) => {
                received = v;
            },
        },
    });
    await contains('input').edit('  New Name  ');
    await press('Enter');
    await tick();
    expect(received).toBe('New Name');
    expect(closed).toBe(true);
});

test('RenameDialog Enter with unchanged value is a noop', async () => {
    const env = await makeDialogMockEnv();
    let attempts = 0;
    await mountWithCleanup(RenameDialog, {
        env,
        props: {
            close: () => {},
            initial: 'Same',
            onConfirm: () => {
                attempts++;
            },
        },
    });
    await press('Enter');
    await tick();
    expect(attempts).toBe(0);
});

test('RenameDialog cancel button closes without invoking onConfirm', async () => {
    const env = await makeDialogMockEnv();
    let confirmed = false;
    let closed = false;
    await mountWithCleanup(RenameDialog, {
        env,
        props: {
            close: () => {
                closed = true;
            },
            initial: 'X',
            onConfirm: () => {
                confirmed = true;
            },
        },
    });
    const cancel = [...document.querySelectorAll('button')].find((b) =>
        /cancel/i.test(b.textContent),
    );
    expect(cancel).not.toBe(undefined);
    cancel.click();
    await tick();
    expect(closed).toBe(true);
    expect(confirmed).toBe(false);
});
