import { browser } from '@web/core/browser/browser';
import { _t } from '@web/core/l10n/translation';
import { user } from '@web/core/user';
import { patch } from '@web/core/utils/patch';
import { session } from '@web/session';
import { X2ManyField } from '@web/views/fields/x2many/x2many_field';

import { signal } from '@odoo/owl';

import { LIST_MODES } from '@muk_web_list_mode/core/mode_switch/mode_switch';

/**
 * Add the read/edit mode toggle to x2many lists, restoring the mode chosen
 * for the field from local storage and defaulting to the arch.
 */
patch(X2ManyField.prototype, {
    setup() {
        super.setup();
        const { activeActions, editable } = this.archInfo;
        const storedMode = browser.localStorage.getItem(this.modeStorageKey);
        const archEditable = (activeActions?.edit && editable) || this.props.editable;
        const archMode = archEditable ? 'edit' : 'read';
        this.listMode = signal(
            ['read', 'edit'].includes(storedMode) ? storedMode : archMode,
        );
    },
    get hasListModes() {
        return (
            this.props.viewMode === 'list' &&
            !this.props.readonly &&
            this.archInfo.activeActions.edit &&
            this.activeActions.write
        );
    },
    /**
     * Local storage key of the mode, scoped to database, user, model and field.
     * @returns {string}
     */
    get modeStorageKey() {
        const { resModel } = this.props.record;
        return `mk_list_mode,${session.db},${user.userId},${resModel},${this.props.name}`;
    },
    /**
     * The toggle shown in the list header: the icon of the current mode and a
     * tooltip naming the mode a click switches to.
     * @returns {object} with a ``mode``, an ``icon``, a ``title`` and ``toggle``
     */
    get modeSwitch() {
        const mode = this.listMode();
        const current = LIST_MODES.find((entry) => entry.mode === mode);
        const next = LIST_MODES.find((entry) => entry.mode !== mode);
        return {
            mode,
            icon: current.icon,
            title: _t('%(current)s, click for %(next)s', {
                current: current.name,
                next: next.name,
            }),
            toggle: () => {
                this.listMode.set(next.mode);
                browser.localStorage.setItem(this.modeStorageKey, next.mode);
            },
        };
    },
    get rendererProps() {
        const props = super.rendererProps;
        if (this.hasListModes) {
            const edit = this.listMode() === 'edit';
            const { onAdd } = props;
            props.editable = edit ? this.archInfo.editable || 'bottom' : false;
            props.hasOpenFormViewButton = edit ? this.archInfo.openFormView : false;
            props.onAdd = (params) => onAdd({ editable: props.editable, ...params });
            props.modeSwitch = this.modeSwitch;
        }
        return props;
    },
    async openRecord(record) {
        if (this.hasListModes && this.listMode() === 'read') {
            return this._openRecord({ record, context: this.props.context });
        }
        return super.openRecord(record);
    },
});
