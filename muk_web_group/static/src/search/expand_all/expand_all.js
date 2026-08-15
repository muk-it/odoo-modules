import { Component } from '@odoo/owl';
import { registry } from '@web/core/registry';
import { DropdownItem } from '@web/core/dropdown/dropdown_item';

const cogMenuRegistry = registry.category('cogMenu');

/**
 * Collect the folded group configs of a group config tree, at every depth.
 * @param {Object} groups Group configs keyed by group value.
 * @returns {Object[]} Configs of every folded group, deepest ones last.
 */
function collectFoldedConfigs(groups) {
    return Object.values(groups).flatMap((config) => [
        ...(config.isFolded ? [config] : []),
        ...collectFoldedConfigs(config.list.groups || {}),
    ]);
}

/**
 * Cog-menu entry that recursively unfolds every group of the current grouped
 * list or kanban view.
 */
export class ExpandAll extends Component {
    static template = 'muk_web_group.ExpandAll';
    static components = { DropdownItem };
    static props = {};

    /**
     * Unfold every group of the group tree, marking a whole nesting level as
     * open before reloading, so each level costs a single batched request.
     * @returns {Promise<void>}
     */
    async onExpandButtonClicked() {
        const model = this.env.model;
        let foldedConfigs = collectFoldedConfigs(model.root.config.groups);
        while (foldedConfigs.length) {
            for (const config of foldedConfigs) {
                model._updateConfig(config, { isFolded: false }, { reload: false });
            }
            await model.root.load();
            foldedConfigs = collectFoldedConfigs(model.root.config.groups);
        }
        model.notify();
    }
}

export const expandAllItem = {
    Component: ExpandAll,
    groupNumber: 15,
    isDisplayed: async (env) =>
        ['kanban', 'list'].includes(env.config.viewType) && env.model.root.isGrouped,
};

cogMenuRegistry.add('expand-all-menu', expandAllItem, { sequence: 1 });
