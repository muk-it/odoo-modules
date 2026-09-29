import { browser } from '@web/core/browser/browser';
import { user } from '@web/core/user';
import { patch } from '@web/core/utils/patch';
import { session } from '@web/session';
import { ListController } from '@web/views/list/list_controller';

import { LIST_MODES } from '@muk_web_list_mode/core/mode_switch/mode_switch';

/**
 * Add a read/edit mode switch to list views, restoring the per-action mode
 * choice from local storage on setup.
 */
patch(ListController.prototype, {
    setup() {
        super.setup();
        if (this.hasListModes) {
            const storedMode = browser.localStorage.getItem(this.getModeStorageKey());
            if (['read', 'edit'].includes(storedMode)) {
                this.applyListMode(storedMode);
            }
        }
    },
    get hasListModes() {
        return !this.props.readonly && this.activeActions.edit;
    },
    /**
     * The modes offered in the control panel switch.
     * @returns {object[]} entries with a ``mode``, a ``name`` and an ``icon``
     */
    get listModes() {
        return LIST_MODES;
    },
    get listMode() {
        return this.editable ? 'edit' : 'read';
    },
    /**
     * Local storage key of the mode, scoped to database, user, action and model.
     * @returns {string}
     */
    getModeStorageKey() {
        const { actionId } = this.env.config;
        return `mk_list_mode,${session.db},${user.userId},${actionId},${this.props.resModel}`;
    },
    /**
     * Make the list inline editable at the arch position, with multi-edit,
     * or open records in the form view.
     * @param {string} mode ``read`` or ``edit``
     */
    applyListMode(mode) {
        const edit = mode === 'edit';
        this.editable = edit ? this.archInfo.editable || 'bottom' : false;
        this.hasOpenFormViewButton = edit ? this.archInfo.openFormView : false;
        this.model.multiEdit = edit || this.archInfo.multiEdit;
    },
    /**
     * Switch to the given mode and remember it for the action.
     * @param {string} mode one of the ``listModes``
     */
    setListMode(mode) {
        this.applyListMode(mode);
        if (this.env.config.actionId) {
            browser.localStorage.setItem(this.getModeStorageKey(), mode);
        }
        this.model.notify();
    },
    get display() {
        const display = super.display;
        if (
            this.hasListModes &&
            display.controlPanel &&
            !this.env.inDialog &&
            !this.uiService.isSmall
        ) {
            display.controlPanel.modeSwitch = {
                mode: this.listMode,
                entries: this.listModes,
                select: (mode) => this.setListMode(mode),
            };
        }
        return display;
    },
});
