import { patch } from '@web/core/utils/patch';
import { SelectionBox } from '@web/views/view_components/selection_box';

/** Count the matching records of a treelist, not its roots or context rows. */
patch(SelectionBox.prototype, {
    get nbTotal() {
        if (this.root.isTree && this.isDomainSelected) {
            return this.root.domainCount;
        }
        return super.nbTotal;
    },
    get isPageSelected() {
        if (!this.root.isTree) {
            return super.isPageSelected;
        }
        return this.nbSelected === this.root.selectableRecords.length;
    },
});
