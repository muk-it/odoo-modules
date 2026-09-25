import { registry } from '@web/core/registry';

import { listView } from '@web/views/list/list_view';

registry.category('views').add('product_search_list', {
    ...listView,
    buttonTemplate: 'muk_product.ListView.Buttons',
});
