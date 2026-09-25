import { browser } from '@web/core/browser/browser';
import { registry } from '@web/core/registry';
import { DynamicRecordList } from '@web/model/relational_model/dynamic_record_list';
import { Record as RelationalRecord } from '@web/model/relational_model/record';
import { RelationalModel } from '@web/model/relational_model/relational_model';
import { getFieldsSpec } from '@web/model/relational_model/utils';
import { orderByToString } from '@web/search/utils/order_by';

const EMPTY_NODE = Object.freeze({
    level: 0,
    count: 0,
    offset: 0,
    context: false,
    expanded: false,
    rollups: {},
});

/**
 * Read the expanded record ids remembered under the given storage key.
 * @param {string} key
 * @returns {number[] | null}
 */
function readExpandedIds(key) {
    if (!key) {
        return null;
    }
    try {
        const value = JSON.parse(browser.localStorage.getItem(key));
        return Array.isArray(value) ? value : null;
    } catch {
        return null;
    }
}

/**
 * Remember the expanded record ids under the given storage key.
 * @param {string} key
 * @param {number[]} ids
 */
function writeExpandedIds(key, ids) {
    if (!key) {
        return;
    }
    try {
        browser.localStorage.setItem(key, JSON.stringify(ids));
    } catch {
        return;
    }
}

/**
 * Record of a treelist, which knows its place in the tree and cannot be
 * selected as a context row.
 */
export class TreeRecord extends RelationalRecord {
    get treeNode() {
        return this.treeList?.tree[this.id] || EMPTY_NODE;
    }
    _toggleSelection(selected) {
        if (!this.treeNode.context) {
            super._toggleSelection(selected);
        }
    }
}

/**
 * Record list of a treelist, or of one of its groups: the page of root
 * records followed, in display order, by the pages of children of the
 * expanded ones.
 */
export class TreeRecordList extends DynamicRecordList {
    get isTree() {
        return Boolean(this.model.treeParentField);
    }
    get context() {
        return {
            ...super.context,
            treelist_parent_field: this.model.treeParentField,
            treelist_search: this.model.treeIsSearching(),
        };
    }
    get isRecordCountTrustable() {
        return !this.isTree;
    }
    get selectableRecords() {
        return this.records.filter((record) => !record.treeNode.context);
    }
    getChildren(record) {
        const index = this.records.indexOf(record);
        const { level } = record.treeNode;
        let end = index + 1;
        while (end < this.records.length && this.records[end].treeNode.level > level) {
            end++;
        }
        return this.records.slice(index + 1, end);
    }
    getChildRecords(parent) {
        const level = parent ? parent.treeNode.level + 1 : 0;
        const records = parent ? this.getChildren(parent) : this.records;
        return records.filter((record) => record.treeNode.level === level);
    }
    getParent(record) {
        const { level } = record.treeNode;
        const index = this.records.indexOf(record);
        for (let position = index - 1; position >= 0; position--) {
            if (this.records[position].treeNode.level < level) {
                return this.records[position];
            }
        }
        return null;
    }
    /**
     * Load the remembered page of children of a record, with their expanded
     * descendants, and insert them below it.
     */
    async expand(record) {
        if (!(await this.leaveEditMode())) {
            return;
        }
        await this.model.mutex.exec(async () => {
            if (!record.treeNode.expanded) {
                await this._loadChildren(
                    record,
                    this.model.treeChildOffsets[record.resId] || 0,
                );
            }
        });
        this.model._addExpandedId(record.resId);
    }
    expandAll() {
        return this._reloadTree({ treeExpandAll: true });
    }
    /**
     * Show another page of children of an expanded record.
     */
    async setChildOffset(record, offset) {
        if (!(await this.leaveEditMode())) {
            return;
        }
        await this.model.mutex.exec(async () => {
            this._removeChildren(record);
            await this._loadChildren(record, offset);
        });
        const { [record.resId]: _previous, ...offsets } = this.model.treeChildOffsets;
        this.model.treeChildOffsets = offset
            ? { ...offsets, [record.resId]: offset }
            : offsets;
    }
    /**
     * Remove the descendant rows of a record without reloading them.
     */
    async collapse(record) {
        if (
            this.getChildren(record).includes(this.editedRecord) &&
            !(await this.leaveEditMode())
        ) {
            return;
        }
        this.model._removeExpandedId(record.resId);
        this._removeChildren(record);
        this.tree[record.id] = { ...record.treeNode, expanded: false };
    }
    async collapseAll() {
        if (!(await this.leaveEditMode())) {
            return;
        }
        this.model._setExpandedIds([]);
        this.model.treeContextIds = [];
        this.model.treeChildOffsets = {};
        this.records = this.records.filter((record) => !record.treeNode.level);
        for (const record of this.records) {
            this.tree[record.id] = { ...record.treeNode, expanded: false };
        }
    }
    /**
     * Insert a new record in edition under the given record, with the parent
     * field prefilled, expanding the record first when needed.
     */
    async addNewChild(record) {
        if (!(await this.leaveEditMode())) {
            return;
        }
        if (!record.treeNode.expanded && record.treeNode.count) {
            await this.expand(record);
        }
        this.model._addExpandedId(record.resId);
        return this.model.mutex.exec(async () => {
            const context = {
                ...this.context,
                [`default_${this.model.treeParentField}`]: record.resId,
            };
            const values = await this.model._loadNewRecord({
                resModel: this.resModel,
                activeFields: this.activeFields,
                fields: this.fields,
                context,
                isMonoRecord: true,
            });
            const child = this._createRecordDatapoint(values, 'edit');
            const node = record.treeNode;
            const index =
                this.records.indexOf(record) + this.getChildren(record).length + 1;
            this._setNode(child, { level: node.level + 1 });
            this.tree[record.id] = { ...node, count: node.count + 1, expanded: true };
            this.records.splice(index, 0, child);
            return child;
        });
    }
    /**
     * Move a record under a parent, after the given sibling or first for a
     * null one, and reload the tree with the parent expanded.
     */
    async moveRecord(record, parent, previous) {
        if (!(await this.leaveEditMode())) {
            return;
        }
        if (parent !== this.getParent(record)) {
            await this.model.orm.write(
                this.resModel,
                [record.resId],
                { [this.model.treeParentField]: parent ? parent.resId : false },
                { context: this.context },
            );
        }
        if (previous !== undefined) {
            const siblings = this.getChildRecords(parent).filter(
                (sibling) => sibling !== record,
            );
            await this._resequence(
                [...siblings, record],
                this.resModel,
                [record.id],
                previous?.id,
            );
        }
        if (parent) {
            this.model._addExpandedId(parent.resId);
        }
        return this.config.isRoot ? this._reloadTree({}) : this.model.load();
    }
    /**
     * Keep the tree information the server sends along each record.
     */
    _setData(data) {
        super._setData(data);
        this.tree = {};
        this.records.forEach((record, index) => {
            this._setNode(record, data.records[index].__tree__);
        });
    }
    _addRecord(record, index) {
        this._setNode(record, {});
        super._addRecord(record, index);
    }
    _setNode(record, node) {
        this.tree[record.id] = { ...EMPTY_NODE, ...node };
        record.treeList = this;
        if (node?.context) {
            record.selected = false;
        }
    }
    async _loadChildren(record, offset) {
        const result = await this.model._readTree(this.config, {
            parentId: record.resId,
            offset,
        });
        const node = record.treeNode;
        const index = this.records.indexOf(record) + 1;
        const children = result.records.map((values) => {
            const child = this._createRecordDatapoint(values);
            child.selected = this.isDomainSelected;
            this._setNode(child, {
                ...values.__tree__,
                level: values.__tree__.level + node.level + 1,
            });
            return child;
        });
        this.records.splice(index, 0, ...children);
        this.tree[record.id] = {
            ...node,
            count: result.length,
            offset,
            expanded: Boolean(children.length),
        };
    }
    _removeChildren(record) {
        const children = this.getChildren(record);
        this.records = this.records.filter((current) => !children.includes(current));
    }
    /**
     * Keep the counts right when an unsaved child row is discarded, as the
     * list count holds the root records only.
     */
    _removeRecords(recordIds) {
        const children = this.records.filter(
            (record) => recordIds.includes(record.id) && record.treeNode.level,
        );
        for (const child of children) {
            const parent = this.getParent(child);
            const node = parent.treeNode;
            this.tree[parent.id] = {
                ...node,
                count: node.count - 1,
                expanded: node.count > 1,
            };
        }
        super._removeRecords(recordIds);
        this.count += children.length;
    }
    /**
     * Count every record of the domain, not only the roots, when the whole
     * domain gets selected, and leave the context rows out of it.
     */
    async _selectDomain(value) {
        if (value && this.isTree) {
            this.domainCount = await this.model.orm.searchCount(
                this.resModel,
                this.domain,
                { context: this.context },
            );
        }
        super._selectDomain(value);
        for (const record of this.records) {
            if (record.treeNode.context) {
                record.selected = false;
            }
        }
    }
    /**
     * Reload the tree with the given model state, keeping the selection.
     */
    async _reloadTree(state) {
        if (!(await this.leaveEditMode())) {
            return;
        }
        const selectedIds = this.selection.map((record) => record.resId);
        Object.assign(this.model, state);
        await this.model.mutex.exec(() =>
            this.model._updateConfig(
                this.config,
                {},
                { commit: this._setData.bind(this) },
            ),
        );
        for (const record of this.records) {
            record.selected =
                !record.treeNode.context && selectedIds.includes(record.resId);
        }
    }
}

/**
 * Relational model of a treelist: reads the records of the list, or of each
 * of its groups, as trees through ``web_tree_read``. The expanded rows and
 * the child pages are shared by all of them.
 */
export class TreeListModel extends RelationalModel {
    static Record = TreeRecord;
    static DynamicRecordList = TreeRecordList;
    setup(params) {
        super.setup(...arguments);
        this.treeParentField = params.treeParentField;
        this.treeRollupFields = params.treeRollupFields || [];
        this.treeStorageKey = params.treeStorageKey;
        this.treeIsSearching = params.treeIsSearching || (() => false);
        const state = params.state?.treeState;
        const storedIds = state ? null : readExpandedIds(this.treeStorageKey);
        this.treeExpandedIds = state?.expandedIds || storedIds || [];
        this.treeContextIds = state?.contextIds || [];
        this.treeChildOffsets = state?.childOffsets || {};
        this.treeExpandAll = !state && !storedIds && Boolean(params.treeExpandAll);
        this.treeExpandContext = false;
    }
    exportState() {
        return {
            ...super.exportState(),
            treeState: {
                expandedIds: this.treeExpandedIds,
                contextIds: this.treeContextIds,
                childOffsets: this.treeChildOffsets,
            },
        };
    }
    /**
     * Expand the ancestors of the matches on the next load after a new search.
     */
    _getNextConfig(currentConfig, params) {
        const config = super._getNextConfig(...arguments);
        if (
            'domain' in params &&
            JSON.stringify(params.domain) !== JSON.stringify(currentConfig.domain)
        ) {
            this.treeExpandContext = true;
            this.treeContextIds = [];
        }
        return config;
    }
    /**
     * Skip the offline availability, the tree is always read online.
     */
    _setAvailableOffline() {}
    /**
     * Count the root records of the tree, as the pager pages through roots.
     */
    async _updateCount(config) {
        if (!this.treeParentField || config.groupBy?.length) {
            return super._updateCount(...arguments);
        }
        const count = await this.keepLast.add(
            this.orm.call(config.resModel, 'web_tree_search_count', [], {
                domain: config.domain,
                parent_field: this.treeParentField,
                search: this.treeIsSearching() && Boolean(config.isRoot),
                context: config.context,
            }),
        );
        config.countLimit = Number.MAX_SAFE_INTEGER;
        return count;
    }
    /**
     * Read the page of roots of a list config, or a page of children of
     * ``parentId``, with their expanded descendants. The ancestors of the
     * matches of a search only show when the list is not grouped.
     */
    _readTree(config, { parentId, offset } = {}) {
        const orderBy = (config.orderBy || []).filter(
            (order) => order.name !== '__count',
        );
        const countLimit = parentId ? undefined : config.countLimit;
        return this.orm.call(config.resModel, 'web_tree_read', [], {
            domain: config.domain,
            specification: getFieldsSpec(
                config.activeFields,
                config.fields,
                config.context,
            ),
            parent_field: this.treeParentField,
            parent_id: parentId,
            search: this.treeIsSearching() && Boolean(config.isRoot),
            offset: parentId ? offset : config.offset,
            limit: config.limit,
            order: orderByToString(orderBy),
            count_limit:
                countLimit && countLimit !== Number.MAX_SAFE_INTEGER
                    ? countLimit + 1
                    : undefined,
            expanded_ids: [...this.treeExpandedIds, ...this.treeContextIds],
            expand_all: !parentId && this.treeExpandAll,
            expand_context: !parentId && this.treeExpandContext,
            rollup_fields: this.treeRollupFields,
            child_offsets: this.treeChildOffsets,
            context: config.context,
        });
    }
    /**
     * Read an ungrouped list, or the list of a group, as a tree and remember
     * the rows it expanded.
     */
    async _loadUngroupedList(config) {
        if (!this.treeParentField) {
            return super._loadUngroupedList(...arguments);
        }
        const result = await this._readTree(config);
        this._keepExpandedIds(result.records);
        if (config.isRoot) {
            this.treeExpandAll = false;
            this.treeExpandContext = false;
        }
        return result;
    }
    /**
     * Read the records of the open groups as trees, one request per group.
     */
    async _postprocessReadGroup(config) {
        const result = await super._postprocessReadGroup(...arguments);
        if (!this.treeParentField) {
            return result;
        }
        const reads = [];
        const collect = (groupsConfig, groups) => {
            for (const group of groups) {
                const groupConfig = groupsConfig[group.value];
                if (group.groups?.length) {
                    collect(groupConfig.list.groups, group.groups);
                } else if (!groupConfig.isFolded && group.records) {
                    reads.push(
                        this._readTree(groupConfig.list).then((tree) => {
                            this._keepExpandedIds(tree.records);
                            group.records = tree.records;
                            group.length = tree.length;
                        }),
                    );
                }
            }
        };
        collect(config.groups, result.groups);
        await Promise.all(reads);
        this.treeExpandAll = false;
        this.treeExpandContext = false;
        return result;
    }
    _keepExpandedIds(records) {
        const emptyIds = new Set(
            records
                .filter((record) => !record.__tree__?.count)
                .map((record) => record.id),
        );
        const expandedIds = this.treeExpandedIds.filter((id) => !emptyIds.has(id));
        const loadedIds = records
            .filter(
                (record) =>
                    record.__tree__?.expanded &&
                    !expandedIds.includes(record.id) &&
                    !this.treeContextIds.includes(record.id),
            )
            .map((record) => record.id);
        if (this.treeExpandAll) {
            expandedIds.push(...loadedIds);
        } else if (this.treeExpandContext) {
            this.treeContextIds = [...this.treeContextIds, ...loadedIds];
        }
        this._setExpandedIds(expandedIds);
    }
    _addExpandedId(resId) {
        this._setExpandedIds([...new Set([...this.treeExpandedIds, resId])]);
    }
    _removeExpandedId(resId) {
        this._setExpandedIds(this.treeExpandedIds.filter((id) => id !== resId));
        this.treeContextIds = this.treeContextIds.filter((id) => id !== resId);
        const { [resId]: _collapsed, ...offsets } = this.treeChildOffsets;
        this.treeChildOffsets = offsets;
    }
    _setExpandedIds(ids) {
        this.treeExpandedIds = ids;
        if (!this.useSampleModel) {
            writeExpandedIds(this.treeStorageKey, ids);
        }
    }
}

registry.category('sample_server').add('web_tree_read', function (params) {
    return this._mockWebSearchReadUnity(params);
});
