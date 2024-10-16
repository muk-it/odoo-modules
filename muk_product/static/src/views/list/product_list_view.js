import { registry } from '@web/core/registry';

import { listView } from '@web/views/list/list_view';
import { ProductListController } from "@muk_product/views/list/product_list_controller";

registry.category('views').add('product_search_list', {
    ...listView,
    Controller: ProductListController,
    buttonTemplate: 'muk_product.ListView.Buttons',
});

