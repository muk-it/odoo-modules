import { expect, test } from '@odoo/hoot';
import { edit, press, waitFor } from '@odoo/hoot-dom';
import { advanceTime, animationFrame, Deferred } from '@odoo/hoot-mock';

import { onRpc } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';
import { setupEditor } from '@html_editor/../tests/_helpers/editor';
import { insertText } from '@html_editor/../tests/_helpers/user_actions';

import '@muk_mail_utils/editor/plugins/canned_response_plugin';

defineMailModels();

test.tags('muk_mail_utils');
test('insert a canned response via the powerbox command', async () => {
    onRpc('mail.canned.response', 'search_read', () => [
        { id: 1, source: 'greeting', substitution: 'Best regards\nMuK IT' },
    ]);
    const { el, editor } = await setupEditor('<p>Hello []</p>');
    await insertText(editor, '/canned');
    await animationFrame();
    await expect('.o-we-powerbox').toHaveCount(1);
    await press('enter');
    await waitFor('.mk_canned_response_list .list-group-item');
    await press('enter');
    await animationFrame();
    expect(el.innerHTML.includes('Best regards<br>MuK IT')).toBe(true);
    expect('.mk_canned_response_dialog').toHaveCount(0);
});

test.tags('muk_mail_utils');
test('canned response dialog filters on search input', async () => {
    const greeting = { id: 1, source: 'greeting', substitution: 'Hello there' };
    const closing = { id: 2, source: 'closing', substitution: 'Best regards' };
    onRpc('mail.canned.response', 'search_read', ({ args }) => {
        const domain = args[0] || [];
        return domain.length ? [closing] : [greeting, closing];
    });
    const { editor } = await setupEditor('<p>[]</p>');
    await insertText(editor, '/canned');
    await animationFrame();
    await press('enter');
    await waitFor('.mk_canned_response_list .list-group-item');
    expect('.mk_canned_response_list .list-group-item').toHaveCount(2);
});

test.tags('muk_mail_utils');
test('canned response dialog drops a superseded search result', async () => {
    const greeting = { id: 1, source: 'greeting', substitution: 'Hello there' };
    const closing = { id: 2, source: 'closing', substitution: 'Best regards' };
    const slowSearch = new Deferred();
    let callCount = 0;
    onRpc('mail.canned.response', 'search_read', async () => {
        callCount++;
        if (callCount === 2) {
            await slowSearch;
            return [greeting, closing];
        }
        return [closing];
    });
    const { editor } = await setupEditor('<p>[]</p>');
    await insertText(editor, '/canned');
    await animationFrame();
    await press('enter');
    await waitFor('.mk_canned_response_dialog input');
    await edit('gre');
    await advanceTime(250);
    await animationFrame();
    await edit('greeting');
    await advanceTime(250);
    await animationFrame();
    expect('.mk_canned_response_list .list-group-item').toHaveCount(1);
    slowSearch.resolve();
    await animationFrame();
    expect('.mk_canned_response_list .list-group-item').toHaveCount(1);
});
