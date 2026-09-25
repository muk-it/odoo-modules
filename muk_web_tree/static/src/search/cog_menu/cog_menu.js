import { patch } from '@web/core/utils/patch';
import { exportAllItem } from '@web/views/list/export_all/export_all';

import { importRecordsItem } from '@base_import/import_records/import_records';

import {
    CollapseAll,
    collapseAllItem,
} from '@muk_web_group/search/collapse_all/collapse_all';
import { ExpandAll, expandAllItem } from '@muk_web_group/search/expand_all/expand_all';

/**
 * Whether the view is an ungrouped treelist, whose rows are expanded instead
 * of its groups.
 * @param {object} env the environment of the cog menu
 * @returns {boolean}
 */
function isTreeList(env) {
    return env.config.viewType === 'treelist' && !env.searchModel.groupBy.length;
}

/**
 * Present a treelist environment as a list one, for the cog menu entries
 * that only know the list view.
 * @param {object} env the environment of the cog menu
 * @returns {object}
 */
function asListEnv(env) {
    const config = Object.create(env.config, { viewType: { value: 'list' } });
    return Object.create(env, { config: { value: config } });
}

for (const item of [exportAllItem, importRecordsItem]) {
    /** Show the list-only cog entries on a treelist. */
    patch(item, {
        isDisplayed(env) {
            return super.isDisplayed(
                env.config.viewType === 'treelist' ? asListEnv(env) : env,
            );
        },
    });
}

for (const item of [expandAllItem, collapseAllItem]) {
    /** Offer Expand All and Collapse All on a treelist. */
    patch(item, {
        isDisplayed(env) {
            return env.config.viewType === 'treelist' || super.isDisplayed(env);
        },
    });
}

/** Expand the tree rows of an ungrouped treelist. */
patch(ExpandAll.prototype, {
    onExpandButtonClicked() {
        if (isTreeList(this.env)) {
            return this.env.model.root.expandAll();
        }
        return super.onExpandButtonClicked();
    },
});

/** Collapse the tree rows of an ungrouped treelist. */
patch(CollapseAll.prototype, {
    onCollapseButtonClicked() {
        if (isTreeList(this.env)) {
            return this.env.model.root.collapseAll();
        }
        return super.onCollapseButtonClicked();
    },
});
