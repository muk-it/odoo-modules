import { registry } from '@web/core/registry';
import { listView } from '@web/views/list/list_view';

import { TreeListArchParser } from './treelist_arch_parser';
import { TreeListController } from './treelist_controller';
import { TreeListModel } from './treelist_model';
import { TreeListRenderer } from './treelist_renderer';

export const treeListView = {
    ...listView,
    type: 'treelist',
    ArchParser: TreeListArchParser,
    Controller: TreeListController,
    Model: TreeListModel,
    Renderer: TreeListRenderer,
};

registry.category('views').add('treelist', treeListView);
