import { ListRenderer } from '@web/views/list/list_renderer';

/** List renderer that mirrors cell clicks and keyboard focus into the preview pane. */
export class MessageListRenderer extends ListRenderer {
    static props = [...ListRenderer.props, 'setSelectedRecord?'];
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
            const records = this.props.list.records.filter((x) => x.id === dataPointId);
            if (records[0]) {
                this.props.setSelectedRecord(records[0]);
            }
        }
        return futureCell;
    }
}
