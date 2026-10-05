import { describe, expect, test, waitFor } from '@odoo/hoot';
import { click } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
import {
    makeServerError,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
} from '@web/../tests/web_test_helpers';
import { session } from '@web/session';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { FileModel } from '@web/core/file_viewer/file_model';
import { FileViewer } from '@web/core/file_viewer/file_viewer';

describe.current.tags('muk_web_preview');
defineMailModels();

function makeFile(id, name, mimetype) {
    return Object.assign(new FileModel(), { id, name, mimetype });
}

function mountViewer(files) {
    return mountWithCleanup(FileViewer, { props: { files, startIndex: 0 } });
}

test('tables, emails and source code open in the text preview', async () => {
    const files = [
        makeFile(1, 'prices.csv', 'text/csv'),
        makeFile(2, 'prices.tsv', 'text/tab-separated-values'),
        makeFile(3, 'export.csv', 'application/octet-stream'),
        makeFile(4, 'mail.eml', 'message/rfc822'),
        makeFile(5, 'mail.msg', 'application/vnd.ms-outlook'),
        makeFile(6, 'outlook.msg', 'application/octet-stream'),
    ];
    await mountViewer(files);
    for (const file of files) {
        await waitFor('.o-FileViewer-view.o-isText');
        expect('.o-FileViewer-view.o-isText').toHaveAttribute(
            'data-src',
            new RegExp(
                `/mail/attachment/render_text/${file.id}[?]filename=${file.name}$`,
            ),
        );
        await click('.o-FileViewer-navigation[aria-label="Next"]');
        await animationFrame();
    }
    const script = makeFile(7, 'script.py', 'text/x-python');
    expect(script.isViewable).toBe(true);
    expect(script.defaultSource).toMatch(/[/]web[/]content[/]7[?]filename=script.py$/);
    expect(makeFile(8, 'archive.zip', 'application/zip').isViewable).toBe(false);
});

test('Office files stay downloads while the Office preview is off', async () => {
    expect(makeFile(1, 'offer.docx', 'application/octet-stream').isViewable).toBe(
        false,
    );
    patchWithCleanup(session, { preview_office_enabled: true });
    expect(makeFile(1, 'offer.docx', 'application/octet-stream').isViewable).toBe(true);
    expect(makeFile(2, 'sheet', 'application/vnd.ms-excel').isViewable).toBe(true);
    const outlook = makeFile(3, 'mail.msg', 'application/vnd.ms-excel');
    expect(outlook.isOffice).toBe(false);
    expect(outlook.isText).toBe(true);
});

test('an Office file opens in the Office Online viewer', async () => {
    patchWithCleanup(session, { preview_office_enabled: true });
    onRpc('/muk_web_preview/office/1', () => 'https://view.example/embed?src=1');
    onRpc('/muk_web_preview/office/3', () => {
        throw makeServerError({ message: 'Not found' });
    });
    await mountViewer([
        makeFile(1, 'offer.docx', 'application/msword'),
        makeFile(2, 'logo.png', 'image/png'),
        makeFile(3, 'broken.pptx', 'application/vnd.ms-powerpoint'),
    ]);
    await waitFor('iframe.mk_office_preview');
    expect('iframe.mk_office_preview').toHaveAttribute(
        'data-src',
        'https://view.example/embed?src=1',
    );
    await click('.o-FileViewer-navigation[aria-label="Next"]');
    await animationFrame();
    expect('.mk_office_preview').toHaveCount(0);
    await click('.o-FileViewer-navigation[aria-label="Next"]');
    await waitFor('.mk_office_preview_error');
    expect('.mk_office_preview_error').toHaveText(/not available/);
});

test('a late viewer URL of a file that is no longer shown is dropped', async () => {
    patchWithCleanup(session, { preview_office_enabled: true });
    const late = Promise.withResolvers();
    onRpc('/muk_web_preview/office/1', () => late.promise);
    onRpc('/muk_web_preview/office/2', () => 'https://view.example/embed?src=2');
    await mountViewer([
        makeFile(1, 'first.docx', 'application/msword'),
        makeFile(2, 'second.docx', 'application/msword'),
    ]);
    expect('.o-FileViewer-main .oi-spin').toHaveCount(1);
    await click('.o-FileViewer-navigation[aria-label="Next"]');
    await waitFor('iframe.mk_office_preview');
    late.resolve('https://view.example/embed?src=1');
    await animationFrame();
    expect('iframe.mk_office_preview').toHaveAttribute(
        'data-src',
        'https://view.example/embed?src=2',
    );
});
