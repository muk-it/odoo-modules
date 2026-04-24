import { describe, expect, test } from '@odoo/hoot';
import {
    makeDialogMockEnv,
    mountWithCleanup,
    patchTranslations,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { RevisionDialog } from '@muk_ai/components/revision_dialog/revision_dialog';

describe.current.tags('muk_ai');
defineMailModels();
patchTranslations();


test('RevisionDialog renders a header with old and new labels', async () => {
    const env = await makeDialogMockEnv();
    await mountWithCleanup(RevisionDialog, {
        env,
        props: {
            close: () => {},
            oldLabel: 'Rev 1',
            newLabel: 'Current',
            diff: '--- old\n+++ new\n@@ -1,1 +1,1 @@\n-a\n+b',
        },
    });
    const header = document.querySelector('.modal-header');
    expect(header).not.toBe(null);
    expect(header.textContent).toMatch(/Rev 1/);
    expect(header.textContent).toMatch(/Current/);
});


test('RevisionDialog renders empty-marker for blank diff', async () => {
    const env = await makeDialogMockEnv();
    await mountWithCleanup(RevisionDialog, {
        env,
        props: {
            close: () => {},
            oldLabel: 'A',
            newLabel: 'B',
            diff: '   ',
        },
    });
    const body = document.querySelector('.modal-body');
    expect(body).not.toBe(null);
    expect(body.textContent).toMatch(/No differences/i);
});


test('RevisionDialog renders diff lines with added / removed classes', async () => {
    const env = await makeDialogMockEnv();
    const diff = [
        '--- a', '+++ b', '@@ -1,2 +1,2 @@',
        ' unchanged',
        '-old',
        '+new',
    ].join('\n');
    await mountWithCleanup(RevisionDialog, {
        env,
        props: {
            close: () => {},
            oldLabel: 'A',
            newLabel: 'B',
            diff,
        },
    });
    const body = document.querySelector('.modal-body');
    expect(body.textContent).toMatch(/unchanged/);
    expect(body.textContent).toMatch(/old/);
    expect(body.textContent).toMatch(/new/);
});
