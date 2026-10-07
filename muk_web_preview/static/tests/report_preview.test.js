import { afterEach, describe, expect, resize, test } from '@odoo/hoot';
import { click, waitFor } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
import {
    contains,
    defineActions,
    defineModels,
    fields,
    getService,
    models,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
} from '@web/../tests/web_test_helpers';
import { browser } from '@web/core/browser/browser';
import { download } from '@web/core/network/download';
import { session } from '@web/session';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { downloadReport } from '@web/webclient/actions/reports/utils';
import { WebClient } from '@web/webclient/webclient';

describe.current.tags('muk_web_preview');

class Partner extends models.Model {
    name = fields.Char();
    _records = [
        { id: 1, name: 'Anna' },
        { id: 2, name: 'Bert' },
    ];
    _views = {
        form: '<form><field name="name"/></form>',
        list: '<list><field name="name"/></list>',
        search: '<search/>',
    };
}

defineMailModels();
defineModels([Partner]);
defineActions([
    {
        id: 1,
        name: 'Partners',
        res_model: 'partner',
        views: [
            [false, 'list'],
            [false, 'form'],
        ],
    },
    {
        id: 7,
        name: 'Partner Card',
        report_name: 'partner_card',
        report_type: 'qweb-pdf',
        type: 'ir.actions.report',
    },
    {
        id: 8,
        name: 'Partner Label',
        report_name: 'partner_label',
        report_type: 'qweb-text',
        type: 'ir.actions.report',
    },
]);

afterEach(() => {
    delete downloadReport.reportingEngineStatusProm;
});

function setUp(reports) {
    Partner._toolbar = { print: reports.map((id) => ({ id, name: `Report ${id}` })) };
    onRpc('/report/get_pdf_engine_state', () => 'ok');
    patchWithCleanup(download, {
        _download: ({ url, data }) => {
            expect.step(`download ${url} ${JSON.parse(data.data)[0]}`);
        },
    });
    patchWithCleanup(browser, {
        open: (url) => {
            const { pathname, searchParams } = new URL(url);
            expect.step(`tab ${pathname} ${JSON.parse(searchParams.get('data'))[0]}`);
            return {};
        },
    });
}

async function openForm() {
    await mountWithCleanup(WebClient);
    await getService('action').doAction(1, { viewType: 'form', props: { resId: 1 } });
    await contains('.o_cp_action_menus button').click();
}

test('the eye of a print item shows the report in the file viewer', async () => {
    setUp([7, 8]);
    await openForm();
    await contains('.o-dropdown-item:contains(Print)').click();
    expect('.mk_report_preview').toHaveCount(2);
    await click('.o-dropdown-item:contains(Report 7) .mk_report_preview');
    await waitFor('.o-FileViewer iframe');
    expect('.o-FileViewer iframe').toHaveAttribute(
        'data-src',
        /pdfjs.*web_preview%2Freport%3Fdata%3D.*partner_card%252F1/,
    );
    expect('.o-FileViewer-header').toHaveText(/Partner Card/);
    await click('.o-FileViewer-header .o-FileViewer-download');
    await animationFrame();
    expect.verifySteps(['download /report/download /report/pdf/partner_card/1']);
});

test('a single print item has the eye too, and text reports open as text', async () => {
    setUp([8]);
    await openForm();
    await click('.mk_report_preview');
    await waitFor('.o-FileViewer-view.o-isText');
    expect('.o-FileViewer-view.o-isText').toHaveAttribute(
        'data-src',
        /[/]web_preview[/]report[?]data=.*partner_label%2F1/,
    );
    expect.verifySteps([]);
});

test('a downloaded report opens in a new tab when the settings ask for it', async () => {
    setUp([7]);
    await mountWithCleanup(WebClient);
    await getService('action').doAction(7, {
        additionalContext: { active_ids: [1] },
    });
    expect.verifySteps(['download /report/download /report/pdf/partner_card/1']);
    patchWithCleanup(session, { preview_report_open: true });
    await getService('action').doAction(7, {
        additionalContext: { active_ids: [2] },
    });
    expect.verifySteps([
        'tab /web_preview/report /report/pdf/partner_card/2',
        'download /report/download /report/pdf/partner_card/2',
    ]);
    expect('.o_notification').toHaveCount(0);
    patchWithCleanup(browser, { open: () => null });
    await getService('action').doAction(7, {
        additionalContext: { active_ids: [2] },
    });
    expect.verifySteps(['download /report/download /report/pdf/partner_card/2']);
    await waitFor('.o_notification');
    expect('.o_notification').toHaveText(/blocked the report tab/);
});

test('a small screen has no eye and opens no tab for a downloaded report', async () => {
    setUp([7]);
    patchWithCleanup(session, { preview_report_open: true });
    await resize({ width: 375, height: 667 });
    await openForm();
    expect('.o-dropdown-item:contains(Report 7)').toHaveCount(1);
    expect('.mk_report_preview').toHaveCount(0);
    await click('.o-dropdown-item:contains(Report 7)');
    await expect.waitForSteps(['download /report/download /report/pdf/partner_card/1']);
});

test('the list print menu previews the selected records', async () => {
    setUp([7]);
    await mountWithCleanup(WebClient);
    await getService('action').doAction(1);
    await contains('.o_data_row:eq(1) .o_list_record_selector input').click();
    await contains('.o_cp_action_menus button:contains(Print)').click();
    await click('.mk_report_preview');
    await waitFor('.o-FileViewer iframe');
    expect('.o-FileViewer iframe').toHaveAttribute('data-src', /partner_card%252F2/);
    expect.verifySteps([]);
});
