import { patch } from '@web/core/utils/patch';

import {
    setColumnWidth,
    removeColumnWidth,
} from '@muk_web_list_column/views/list/list_view_storage';

import { ListRenderer } from '@web/views/list/list_renderer';

/** Persist column widths on manual resize and clear them on a reset double-click. */
patch(ListRenderer.prototype, {
    onStartResizeWithSave(ev) {
        this.columnWidths.onStartResize(ev);
        const th = ev.target.closest('th');
        const resizeStoppingEvents = ['keydown', 'pointerdown', 'pointerup'];
        const saveWidth = (ev) => {
            if (ev && ev.type === 'pointerdown' && ev.button === 0) {
                return;
            }
            if (th.style.width && th.dataset.name) {
                setColumnWidth(
                    this.props.list.resModel,
                    th.dataset.name,
                    th.style.width,
                );
            }
            for (const eventType of resizeStoppingEvents) {
                window.removeEventListener(eventType, saveWidth);
            }
            document.activeElement.blur();
        };
        for (const eventType of resizeStoppingEvents) {
            window.addEventListener(eventType, saveWidth);
        }
    },
    onResizeDoubleClickRemoveSave(ev) {
        for (const column of this.columns) {
            removeColumnWidth(this.props.list.resModel, column.name);
        }
        this.columnWidths.resetWidths(ev);
    },
});
