import { patch } from '@web/core/utils/patch';

import { ProductDocumentKanbanController } from '@product/js/product_document_kanban/product_document_kanban_controller';

/** Skip the inline upload form when no target record is provided by context. */
patch(ProductDocumentKanbanController.prototype, {
    setup() {
        super.setup();
        if (
            !this.props.context.default_res_model ||
            !this.props.context.default_res_id
        ) {
            this.formData = false;
        }
    },
});
