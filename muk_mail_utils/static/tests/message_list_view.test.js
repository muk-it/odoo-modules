import { expect, test } from "@odoo/hoot";

import {
    defineModels,
    fields,
    models,
    mountView,
    contains,
    serverState,
} from "@web/../tests/web_test_helpers";
import { 
    defineMailModels, 
    patchUiSize, 
    SIZES 
} from "@mail/../tests/mail_test_helpers";

import "@muk_mail_utils/views/message_list/message_list_view";
class TestMessage extends models.Model {
    _name = "x_test_message";
    _records = [
        {
            id: 1,
            author_id: serverState.partnerId,
            notified_partner_ids: [serverState.odoobotId],
            attachment_ids: [],
            body: "<p>Hello from first</p>",
        },
        {
            id: 2,
            author_id: serverState.odoobotId,
            notified_partner_ids: [serverState.partnerId],
            attachment_ids: [],
            body: "<p>Hello from second</p>",
        },
    ];
    body = fields.Html();
    author_id = fields.Many2one({ relation: "res.partner" });
    notified_partner_ids = fields.Many2many({ relation: "res.partner" });
    attachment_ids = fields.Many2many({ relation: "ir.attachment" });
}

defineMailModels();
defineModels({ TestMessage });

test.tags("muk_mail_utils");
test("message preview is only enabled on XXL screens", async () => {
    patchUiSize({ size: SIZES.SM });
    await mountView({
        type: "list",
        resModel: "x_test_message",
        arch: `
            <list js_class="message_list">
                <field name="author_id"/>
                <field name="body"/>
            </list>
        `,
    });
    expect(".mk_message_list_view").toHaveCount(1);
    expect(".mk_message_preview").toHaveCount(0);
});

test.tags("muk_mail_utils");
test("selecting a row updates the message preview", async () => {
    patchUiSize({ size: SIZES.XXL });
    await mountView({
        type: "list",
        resModel: "x_test_message",
        arch: `
            <list js_class="message_list">
                <field name="author_id"/>
                <field name="body"/>
            </list>
        `,
    });
    expect(".mk_message_preview").toHaveCount(1);
    expect(".mk_message_preview").toHaveText(/No Preview/);
    await contains(
        ".o_list_table tbody tr.o_data_row:eq(0) td.o_data_cell:eq(0)"
    ).click();
    expect(".mk_message_preview").toHaveText(/Hello from first/);
    await contains(
        ".o_list_table tbody tr.o_data_row:eq(1) td.o_data_cell:eq(0)"
    ).click();
    expect(".mk_message_preview").toHaveText(/Hello from second/);
});
