import { t, useProps } from '@odoo/owl';

import { ListRenderer, listRendererProps } from '@web/views/list/list_renderer';

/** List renderer that mirrors cell clicks and keyboard focus into the preview pane. */
export class MessageListRenderer extends ListRenderer {
    props = useProps({
        ...listRendererProps,
        setSelectedRecord: t.function(),
    });
    onCellClicked(record, column, ev) {
        this.props.setSelectedRecord(record);
        super.onCellClicked(record, column, ev);
    }
    /**
     * Resolve the next focusable cell and preview the record of its row.
     * @param {object} cell the current cell element
     * @param {boolean} cellIsInGroupRow whether the cell sits in a group row
     * @param {string} direction the navigation direction
     * @returns {object} the next focusable cell
     */
    findFocusFutureCell(cell, cellIsInGroupRow, direction) {
        const futureCell = super.findFocusFutureCell(cell, cellIsInGroupRow, direction);
        if (futureCell) {
            const dataPointId = futureCell.closest('tr').dataset.id;
            const record = this.props.list.records.find((x) => x.id === dataPointId);
            if (record) {
                this.props.setSelectedRecord(record);
            }
        }
        return futureCell;
    }
}
