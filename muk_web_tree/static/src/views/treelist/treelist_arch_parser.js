import { exprToBoolean } from '@web/core/utils/strings';
import { ListArchParser } from '@web/views/list/list_arch_parser';

/**
 * Parse a treelist arch as a list arch, plus the tree attributes.
 */
export class TreeListArchParser extends ListArchParser {
    /**
     * Parse the arch as a list, from a copy renamed to ``list``, and add the
     * parent field, the drag option and the rollup columns, which must not
     * use a widget.
     */
    parse(xmlDoc, models, modelName) {
        const listDoc = xmlDoc.ownerDocument.createElement('list');
        for (const attribute of xmlDoc.attributes) {
            listDoc.setAttribute(attribute.name, attribute.value);
        }
        listDoc.append(...xmlDoc.cloneNode(true).childNodes);
        const archInfo = super.parse(listDoc, models, modelName);
        const rollupFields = new Set();
        for (const column of archInfo.columns) {
            const fields = column.type === 'column_group' ? column.fields : [column];
            for (const field of fields) {
                if (
                    field.type === 'field' &&
                    !field.widget &&
                    exprToBoolean(field.attrs?.rollup || '')
                ) {
                    rollupFields.add(field.name);
                }
            }
        }
        return {
            ...archInfo,
            parentField: xmlDoc.getAttribute('parent_field') || 'parent_id',
            draggable: exprToBoolean(xmlDoc.getAttribute('draggable') || ''),
            rollupFields: [...rollupFields],
        };
    }
}
