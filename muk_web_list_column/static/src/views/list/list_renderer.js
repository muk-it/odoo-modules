import { patch } from '@web/core/utils/patch';

import {
    getColumnWidth,
    setColumnWidth,
    removeColumnWidth,
} from '@muk_web_list_column/views/list/list_view_storage';

import { ListRenderer } from '@web/views/list/list_renderer';

/** Apply stored column widths, persist them on manual resize and clear them on reset. */
patch(ListRenderer.prototype, {
    processAllColumn(allColumns, list) {
        return super.processAllColumn(allColumns, list).map((column) => {
            const width = column.hasLabel && getColumnWidth(list.resModel, column.name);
            return width ? { ...column, attrs: { ...column.attrs, width } } : column;
        });
    },
    onStartResizeWithSave(ev, column) {
        this.columnWidths.onStartResize(ev);
        const th = ev.target.closest('th');
        const resizeStoppingEvents = [
            'keydown',
            'pointerdown',
            'pointerup',
            'pointercancel',
        ];
        const saveWidth = (ev) => {
            if (ev.type === 'pointerdown' && ev.button === 0) {
                return;
            }
            if (th.style.width) {
                const { paddingLeft, paddingRight } = getComputedStyle(th);
                const width =
                    parseFloat(th.style.width) -
                    parseFloat(paddingLeft) -
                    parseFloat(paddingRight);
                setColumnWidth(
                    this.props.list.resModel,
                    column.name,
                    `${Math.floor(width)}px`,
                );
            }
            for (const eventType of resizeStoppingEvents) {
                window.removeEventListener(eventType, saveWidth);
            }
        };
        for (const eventType of resizeStoppingEvents) {
            window.addEventListener(eventType, saveWidth);
        }
    },
    onResizeDoubleClickRemoveSave() {
        for (const column of this.columns) {
            removeColumnWidth(this.props.list.resModel, column.name);
        }
        this.allColumns = this.processAllColumn(
            this.props.archInfo.columns,
            this.props.list,
        );
        this.columns = this.getActiveColumns();
        this.columnWidths.resetWidths();
    },
});
