import { Component } from '@odoo/owl';
import { categoryBadge, categoryLabel } from './utils';

/**
 * Searchable, category-grouped sidebar listing the available tools and emitting
 * selection and search events to the parent.
 */
export class ToolList extends Component {
    static template = 'muk_mcp.ToolList';
    static props = {
        groups: Array,
        selected: { type: [String, { value: null }], optional: true },
        search: String,
        onSearch: Function,
        onSelect: Function,
    };
    setup() {
        this.categoryLabel = categoryLabel;
        this.categoryBadge = categoryBadge;
    }
}
