import { makeActiveField } from '@web/model/relational_model/utils';
import { ListController } from '@web/views/list/list_controller';

/**
 * List controller of a treelist: hands the tree settings of the arch to the
 * model and loads the parent field, so new children keep their parent.
 */
export class TreeListController extends ListController {
    get className() {
        return `${super.className} o_list_view`;
    }
    get modelParams() {
        const params = super.modelParams;
        const { parentField, rollupFields } = this.archInfo;
        const { activeFields, fields } = params.config;
        const actionId = this.env.config.actionId || 0;
        if (!(parentField in activeFields)) {
            activeFields[parentField] = makeActiveField({ invisible: true });
            fields[parentField] ??= this.props.fields[parentField];
        }
        return {
            ...params,
            treeParentField: parentField,
            treeRollupFields: rollupFields,
            treeExpandAll: params.config.openGroupsByDefault,
            treeStorageKey: `mk_treelist,${this.props.resModel},${actionId}`,
            treeIsSearching: () => Boolean(this.env.searchModel?.query.length),
        };
    }
}
