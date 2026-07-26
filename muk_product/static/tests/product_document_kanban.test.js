import { expect, test } from '@odoo/hoot';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';
import {
    defineModels,
    fields,
    findComponent,
    models,
    mountView,
} from '@web/../tests/web_test_helpers';

import { UploadButton } from '@product/js/product_document_kanban/upload_button/upload_button';

import '@product/js/product_document_kanban/product_document_kanban_view';
import '@muk_product/views/kanban/document/document_kanban_controller';

class ProductDocument extends models.Model {
    _name = 'product.document';
    _records = [];
    name = fields.Char();
}

defineMailModels();
defineModels([ProductDocument]);

const documentKanbanArch = `
    <kanban js_class="product_documents_kanban">
        <templates>
            <t t-name="card">
                <field name="name"/>
            </t>
        </templates>
    </kanban>
`;

function mountDocumentKanban(context) {
    return mountView({
        type: 'kanban',
        resModel: 'product.document',
        arch: documentKanbanArch,
        context,
    });
}

function uploadFormEntries(view) {
    const uploadButton = findComponent(
        view,
        (component) => component instanceof UploadButton,
    );
    const formData = new FormData();
    uploadButton.buildFormData(formData);
    return [...formData.entries()];
}

test.tags('muk_product_views');
test('document kanban hides the upload button without a target record', async () => {
    await mountDocumentKanban({ create: false });
    expect('.o_kanban_view').toHaveCount(1);
    expect('button[name="product_upload_document"]').toHaveCount(0);
});

test.tags('muk_product_views');
test('document kanban hides the upload button for a half filled target', async () => {
    await mountDocumentKanban({ default_res_model: 'product.template' });
    expect('button[name="product_upload_document"]').toHaveCount(0);
});

test.tags('muk_product_views');
test('document kanban hides the upload button without a target id', async () => {
    await mountDocumentKanban({ default_res_id: 7 });
    expect('button[name="product_upload_document"]').toHaveCount(0);
});

test.tags('muk_product_views');
test('document kanban uploads against the target record from the context', async () => {
    const view = await mountDocumentKanban({
        default_res_model: 'product.template',
        default_res_id: 7,
    });
    expect('button[name="product_upload_document"]').toHaveCount(1);
    expect(uploadFormEntries(view)).toEqual([
        ['res_model', 'product.template'],
        ['res_id', '7'],
    ]);
});
