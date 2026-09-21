import { Component } from '@odoo/owl';
import { registry } from '@web/core/registry';
import { DropdownItem } from '@web/core/dropdown/dropdown_item';

const cogMenuRegistry = registry.category('cogMenu');

/**
 * Cog-menu entry that recursively folds every group of the current grouped
 * list or kanban view.
 */
export class CollapseAll extends Component {
    static template = 'muk_web_group.CollapseAll';
    static components = { DropdownItem };
    /**
     * Walk the group tree breadth-first, toggling every unfolded group closed,
     * then reload the root and notify the model.
     * @returns {Promise<void>}
     */
    async onCollapseButtonClicked() {
        let groups = this.env.model.root.groups;
        while (groups.length) {
            const unfoldedGroups = groups.filter((group) => !group.isFolded);
            if (unfoldedGroups.length) {
                for (const group of unfoldedGroups) {
                    await group.toggle();
                }
            }
            const subGroups = unfoldedGroups.map((group) => group.list.groups || []);
            groups = subGroups.reduce((a, b) => a.concat(b), []);
        }
        await this.env.model.root.load();
        this.env.model.notify();
    }
}

export const collapseAllItem = {
    Component: CollapseAll,
    groupNumber: 3,
    isDisplayed: async (env) =>
        ['kanban', 'list'].includes(env.config.viewType) &&
        env.searchModel.groupBy.length > 0,
};

cogMenuRegistry.add('collapse-all-menu', collapseAllItem, { sequence: 2 });
