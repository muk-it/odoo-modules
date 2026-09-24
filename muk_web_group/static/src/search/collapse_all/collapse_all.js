import { Component } from '@odoo/owl';
import { registry } from '@web/core/registry';
import { DropdownItem } from '@web/core/dropdown/dropdown_item';

const cogMenuRegistry = registry.category('cogMenu');

/**
 * Whether the view shows groups that can be folded: a grouped list, or a grouped
 * kanban on a large screen, since a small-screen kanban never folds its columns.
 * @param {object} env the environment of the cog menu
 * @returns {boolean} true when collapse and expand all apply
 */
export function hasFoldableGroups(env) {
    const viewType = env.config.viewType;
    return (
        env.searchModel.groupBy.length > 0 &&
        (viewType === 'list' || (viewType === 'kanban' && !env.services.ui.isSmall))
    );
}

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
    isDisplayed: async (env) => hasFoldableGroups(env),
};

cogMenuRegistry.add('collapse-all-menu', collapseAllItem, { sequence: 2 });
