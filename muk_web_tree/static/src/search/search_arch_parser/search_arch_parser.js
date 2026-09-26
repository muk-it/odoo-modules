import { patch } from '@web/core/utils/patch';
import { SearchArchParser } from '@web/search/search_arch_parser';

/** Show a search panel on a treelist wherever it is shown on a list. */
patch(SearchArchParser.prototype, {
    visitSearchPanel(searchPanelNode) {
        super.visitSearchPanel(searchPanelNode);
        const { viewTypes } = this.searchPanelInfo;
        if (viewTypes.includes('list') && !viewTypes.includes('treelist')) {
            this.searchPanelInfo.viewTypes = [...viewTypes, 'treelist'];
        }
    },
});
