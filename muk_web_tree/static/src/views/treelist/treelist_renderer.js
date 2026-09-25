import { browser } from '@web/core/browser/browser';
import { _t } from '@web/core/l10n/translation';
import { useDraggable } from '@web/core/utils/draggable';
import { ListRenderer } from '@web/views/list/list_renderer';
import { getFormattedValue } from '@web/views/utils';
import { ActionPlugin } from '@web/webclient/actions/action_plugin';

import { signal, usePlugin } from '@odoo/owl';

const DROP_MARKERS = [
    'mk_treelist_drop_target',
    'mk_treelist_drop_above',
    'mk_treelist_drop_below',
];

/**
 * List renderer that nests the records of a treelist under their parents,
 * with a toggle, an indentation and an optional drag handle in the first
 * column.
 */
export class TreeListRenderer extends ListRenderer {
    static template = 'muk_web_tree.TreeListRenderer';
    static recordRowTemplate = 'muk_web_tree.TreeListRenderer.RecordRow';
    action = usePlugin(ActionPlugin);
    treeLoadingId = signal(null);
    setup() {
        super.setup();
        this.dropTarget = null;
        useDraggable({
            ref: this.rootRef,
            elements: '.mk_treelist_draggable',
            handle: '.mk_treelist_handle',
            cursor: 'grabbing',
            enable: () => this.canDragRecords,
            onWillStartDrag: ({ element }) => {
                this.dragCellWidths = [...element.children].map(
                    (cell) => cell.getBoundingClientRect().width,
                );
            },
            onDragStart: ({ element, addClass, addStyle }) => {
                [...element.children].forEach((cell, index) => {
                    addStyle(cell, { width: `${this.dragCellWidths[index]}px` });
                });
                this.dragPlaceholder = element.cloneNode(true);
                this.dragPlaceholder.removeAttribute('style');
                this.dragPlaceholder.className = 'mk_treelist_placeholder';
                element.before(this.dragPlaceholder);
                addClass(element, 'mk_treelist_dragged');
            },
            onDrag: ({ element, y }) => this.updateDropTarget(element, y),
            onDragEnd: () => {
                this.dragPlaceholder?.remove();
                this.dragPlaceholder = null;
                this.updateDropTarget(null);
            },
            onDrop: ({ element }) => this.dropRecord(element),
        });
    }
    get isTree() {
        return Boolean(this.props.list.model.treeParentField);
    }
    get treeRendererClass() {
        return {
            mk_treelist_draggable_rows: this.canDragRecords,
            mk_treelist_addable_rows: this.canAddChild,
        };
    }
    get treeColumn() {
        return this.columns.find(
            (column) => column.type === 'field' || column.type === 'column_group',
        );
    }
    get canDragRecords() {
        return Boolean(
            this.isTree &&
            (this.props.archInfo.draggable || this.canReorderRecords) &&
            this.props.activeActions?.edit !== false &&
            !this.props.list.model.useSampleModel,
        );
    }
    get canReorderRecords() {
        const { handleField, orderBy } = this.props.list;
        return Boolean(
            handleField && (!orderBy.length || orderBy[0].name === handleField),
        );
    }
    getActiveColumns() {
        const columns = super.getActiveColumns();
        return this.isTree
            ? columns.filter((column) => column.widget !== 'handle')
            : columns;
    }
    get canAddChild() {
        return Boolean(
            this.isTree &&
            this.props.activeActions?.create !== false &&
            !this.props.list.model.useSampleModel,
        );
    }
    get selectAll() {
        const list = this.props.list;
        if (!this.isTree || list.isGrouped || list.isDomainSelected) {
            return super.selectAll;
        }
        const count = list.selectableRecords.length;
        return count > 0 && list.selection.length === count;
    }
    get someSelected() {
        const list = this.props.list;
        if (!this.isTree || list.isGrouped) {
            return super.someSelected;
        }
        const count = list.selectableRecords.length;
        return list.selection.length > 0 && list.selection.length < count;
    }
    /**
     * Add the next sibling right away when a new child row is confirmed, so
     * several children can be typed in a row.
     */
    editNextRecord(record) {
        const parent =
            this.isTree && record.isNew && record.treeList?.getParent(record);
        if (parent) {
            return this.onAddChild(parent);
        }
        return super.editNextRecord(...arguments);
    }
    isTreeColumn(column) {
        return this.isTree && column === this.treeColumn;
    }
    getTreeNode(record) {
        return record.treeNode;
    }
    getTreeRowLevel(record) {
        return this.isTree ? this.getTreeNode(record).level + 1 : undefined;
    }
    getTreeRowExpanded(record) {
        if (!this.isTree || !this.getTreeNode(record).count) {
            return undefined;
        }
        return this.getTreeNode(record).expanded ? 'true' : 'false';
    }
    getTreeCellStyle(column, record) {
        if (!this.isTreeColumn(column)) {
            return undefined;
        }
        return `--mk-treelist-level: ${this.getTreeNode(record).level}`;
    }
    getRowClass(record) {
        const classNames = super.getRowClass(record);
        if (!this.isTree) {
            return classNames;
        }
        const extraClasses = [];
        if (this.getTreeNode(record).context) {
            extraClasses.push('mk_treelist_context');
        }
        if (this.canDragRecords && record.resId) {
            extraClasses.push('mk_treelist_draggable');
        }
        return [classNames, ...extraClasses].filter(Boolean).join(' ');
    }
    getColumnClass(column) {
        const classNames = super.getColumnClass(column);
        return this.isTreeColumn(column)
            ? `${classNames} mk_treelist_header`
            : classNames;
    }
    getTreeCellTitle(column, record) {
        if (this.getRollupValue(column, record) !== undefined) {
            return _t('Total including the children');
        }
        return undefined;
    }
    getTreeToggleLabel(record) {
        return this.getTreeNode(record).expanded ? _t('Collapse') : _t('Expand');
    }
    showTreePager(record) {
        const node = this.getTreeNode(record);
        return node.expanded && node.count > record.treeList.limit;
    }
    getTreePagerProps(record) {
        const node = this.getTreeNode(record);
        return {
            offset: node.offset,
            limit: record.treeList.limit,
            total: node.count,
            isEditable: false,
            withAccessKey: false,
            onUpdate: ({ offset }) => record.treeList.setChildOffset(record, offset),
        };
    }
    getGroupPagerProps(group) {
        const props = super.getGroupPagerProps(group);
        return group.list.isGrouped ? props : { ...props, total: group.list.count };
    }
    getCellClass(column, record) {
        const classNames = [super.getCellClass(column, record)];
        if (this.isTreeColumn(column)) {
            classNames.push('mk_treelist_cell');
        }
        if (this.getRollupValue(column, record) !== undefined) {
            classNames.push('mk_treelist_rollup');
        }
        return classNames.join(' ');
    }
    isRollupColumn(column) {
        return this.isTree && this.props.archInfo.rollupFields.includes(column.name);
    }
    getRollupValue(column, record) {
        if (!this.isRollupColumn(column) || !this.getTreeNode(record).count) {
            return undefined;
        }
        return this.getTreeNode(record).rollups[column.name];
    }
    /**
     * Format the subtree total instead of the own value on parent rows of a
     * rollup column.
     */
    getFormattedValue(column, record) {
        const rollup = this.getRollupValue(column, record);
        if (rollup === undefined) {
            return super.getFormattedValue(column, record);
        }
        return getFormattedValue(
            { fields: record.fields, data: { ...record.data, [column.name]: rollup } },
            column.name,
            column,
        );
    }
    /**
     * Sum the footer over the matching rows only, and for rollup columns over
     * the subtree totals of the roots, so no record is counted twice.
     */
    computeAggregates() {
        const aggregates = super.computeAggregates();
        const list = this.props.list;
        if (!this.isTree || list.isGrouped || list.selection.length) {
            return aggregates;
        }
        const roots = list.records.filter((record) => !this.getTreeNode(record).level);
        for (const column of this.columns) {
            if (!(column.name in aggregates) || !column.attrs?.sum) {
                continue;
            }
            const rollup = this.isRollupColumn(column);
            const records = rollup ? roots : list.selectableRecords;
            const total = records.reduce((sum, record) => {
                const value = rollup ? this.getRollupValue(column, record) : undefined;
                return sum + (value ?? (record.data[column.name] || 0));
            }, 0);
            const formatted = getFormattedValue(
                { fields: list.fields, data: { [column.name]: total } },
                column.name,
                column,
            );
            aggregates[column.name] = {
                ...aggregates[column.name],
                value: formatted,
                rawValue: total,
            };
        }
        return aggregates;
    }
    /**
     * Expand or collapse a row, showing a spinner while its children load,
     * and move the focus back to it when ``focus`` is set.
     */
    async toggleRecord(record, focus = false) {
        const node = this.getTreeNode(record);
        if (!node.count || this.treeLoadingId() === record.resId) {
            return;
        }
        const { resId } = record;
        if (node.expanded) {
            await record.treeList.collapse(record);
        } else {
            this.treeLoadingId.set(resId);
            try {
                await record.treeList.expand(record);
            } finally {
                this.treeLoadingId.set(null);
            }
        }
        if (focus) {
            this.focusTreeCell(resId);
        }
    }
    async onAddChild(record) {
        if (this.props.editable) {
            const child = await record.treeList.addNewChild(record);
            if (child) {
                this.cellToFocus = { column: this.treeColumn, record: child };
            }
            return;
        }
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: this.props.list.resModel,
            views: [[false, 'form']],
            target: 'current',
            context: {
                ...record.treeList.context,
                [`default_${this.props.list.model.treeParentField}`]: record.resId,
            },
        });
    }
    focusTreeCell(resId) {
        browser.requestAnimationFrame(() => {
            const cell = this.rootRef()?.querySelector(
                `.o_data_row[data-res-id="${resId}"] .mk_treelist_cell`,
            );
            cell?.focus();
        });
    }
    onCellKeydownReadOnlyMode(hotkey, cell, group, record) {
        if (record && cell.classList.contains('mk_treelist_cell')) {
            const node = this.getTreeNode(record);
            if (hotkey === 'arrowright' && node.count && !node.expanded) {
                this.toggleRecord(record, true);
                return true;
            }
            if (hotkey === 'arrowleft') {
                if (node.count && node.expanded) {
                    this.toggleRecord(record, true);
                    return true;
                }
                const parent = record.treeList?.getParent(record);
                if (parent) {
                    this.focusTreeCell(parent.resId);
                    return true;
                }
            }
        }
        return super.onCellKeydownReadOnlyMode(...arguments);
    }
    findRecord(element) {
        return this.props.list.records.find(
            (record) => record.id === element?.dataset.id,
        );
    }
    isDescendant(record, ancestor) {
        return Boolean(ancestor.treeList?.getChildren(ancestor).includes(record));
    }
    /**
     * Mark where the dragged row would go: under the row below the pointer
     * for its middle half, else next to it, before or after it when the rows
     * are ordered by their handle field.
     */
    updateDropTarget(element, y) {
        const root = this.rootRef();
        root?.classList.remove('mk_treelist_drop_root');
        for (const row of root?.querySelectorAll('.o_data_row') || []) {
            row.classList.remove(...DROP_MARKERS);
        }
        this.dropTarget = null;
        if (!element) {
            return;
        }
        const dragged = this.findRecord(element);
        const row = [...root.querySelectorAll('.o_data_row')].find((current) => {
            const rect = current.getBoundingClientRect();
            return current !== element && y >= rect.top && y <= rect.bottom;
        });
        const target = this.findRecord(row);
        if (
            !target?.resId ||
            target === dragged ||
            this.isDescendant(target, dragged)
        ) {
            return;
        }
        const rect = row.getBoundingClientRect();
        const offset = (y - rect.top) / rect.height;
        const { draggable } = this.props.archInfo;
        const inside = draggable && offset >= 0.25 && offset <= 0.75;
        const parent = inside ? target : target.treeList?.getParent(target);
        const sameParent = parent === dragged.treeList?.getParent(dragged);
        if (!inside && this.canReorderRecords && (sameParent || draggable)) {
            const siblings = target.treeList.getChildRecords(parent);
            const previous =
                offset < 0.5 ? siblings[siblings.indexOf(target) - 1] || null : target;
            if (previous === dragged) {
                return;
            }
            this.dropTarget = { parent, previous };
            row.classList.add(
                offset < 0.5 ? 'mk_treelist_drop_above' : 'mk_treelist_drop_below',
            );
            return;
        }
        if (sameParent || !draggable) {
            return;
        }
        this.dropTarget = { parent };
        if (parent) {
            root.querySelector(`.o_data_row[data-id="${parent.id}"]`)?.classList.add(
                'mk_treelist_drop_target',
            );
        } else {
            root.classList.add('mk_treelist_drop_root');
        }
    }
    /**
     * Move the dropped row to the current drop target.
     */
    async dropRecord(element) {
        const record = this.findRecord(element);
        const target = this.dropTarget;
        this.updateDropTarget(null);
        if (!record || !target) {
            return;
        }
        await record.treeList.moveRecord(record, target.parent, target.previous);
        this.focusTreeCell(record.resId);
    }
}
