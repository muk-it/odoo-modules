// @odoo-module

import { Component, useRef, useState } from '@odoo/owl';

import { browser } from '@web/core/browser/browser';

import { Dropdown } from '@web/core/dropdown/dropdown';
import { DropdownItem } from '@web/core/dropdown/dropdown_item';
import { fuzzyLookup } from '@web/core/utils/search';

/**
 * Searchable single-choice menu exposing the ``SelectMenu`` API.
 *
 * Odoo 16 has no ``@web/core/select_menu``, which only arrived in 17.0, so the
 * subset the icon pickers rely on is built on 16's own ``Dropdown``: the
 * ``choices``/``value``/``onSelect`` contract, a search box and the ``choice``
 * slot rendering one entry. The core class names are kept so a stylesheet
 * written against the later component still lands.
 */
export class SelectMenu extends Component {
    static template = 'muk_ai.CompatSelectMenu';
    static components = { Dropdown, DropdownItem };
    static props = {
        choices: { type: Array, optional: true },
        value: { optional: true },
        class: { type: String, optional: true },
        menuClass: { type: String, optional: true },
        togglerClass: { type: String, optional: true },
        placeholder: { type: String, optional: true },
        searchPlaceholder: { type: String, optional: true },
        required: { type: Boolean, optional: true },
        onSelect: { type: Function, optional: true },
        slots: { type: Object, optional: true },
    };
    static defaultProps = {
        choices: [],
        class: '',
        menuClass: '',
        togglerClass: '',
        placeholder: '',
        searchPlaceholder: '',
        required: false,
        onSelect: () => {},
    };
    setup() {
        this.state = useState({ search: '' });
        this.rootRef = useRef('root');
        this.searchRef = useRef('search');
    }

    /**
     * Choices left after the search box, in their given order.
     * @returns {object[]}
     */
    get displayedChoices() {
        const search = this.state.search.trim();
        if (!search) {
            return this.props.choices;
        }
        return fuzzyLookup(search, this.props.choices, (choice) =>
            String(choice.label ?? choice.value),
        );
    }
    get canDeselect() {
        return (
            !this.props.required && ![undefined, null, false].includes(this.props.value)
        );
    }
    itemClass(choice) {
        return choice.value === this.props.value
            ? 'o_select_menu_item selected'
            : 'o_select_menu_item';
    }
    /**
     * Clear the search and focus its box once the menu is painted.
     * The dropdown owns its open state, so this component is not re-rendered
     * when the menu appears and an effect would never see it. OWL renders on
     * an animation frame it schedules after this call, hence the second one.
     */
    onBeforeOpen() {
        this.state.search = '';
        browser.requestAnimationFrame(() =>
            browser.requestAnimationFrame(() => this.searchRef.el?.focus()),
        );
    }
    onSearchInput(ev) {
        this.state.search = ev.target.value;
    }
    onItemSelected(value) {
        this.props.onSelect(value);
    }
    onClear() {
        this.props.onSelect(undefined);
    }
}
