
import { session } from '@web/session';
import { patch } from '@web/core/utils/patch';
import { _t } from '@web/core/l10n/translation';
import { browser } from '@web/core/browser/browser';

import { ListController } from '@web/views/list/list_controller';

patch(ListController.prototype, {
    setup() {
        super.setup();
        if (!this.props.readonly && this.activeActions.edit &&
            this.env.config.actionId
        ) {
            const storedMode = browser.localStorage.getItem(
                this.getModeStorageKey()
            );
            if (storedMode === 'edit' && !this.editable) {
                this.editable = this.archInfo.editable || 'bottom';
            } else if (storedMode === 'read' && this.editable) {
                this.editable = false;
            }
        }
    },
    getModeStorageKey() {
        const uid = this.env.services?.user?.userId;
        const actionId = this.env.config.actionId;
        const model = this.props.resModel;
        return `mk_list_mode,${session.db},${uid},${actionId},${model}`;
    },
    get display() {
        const res = super.display;
        if (!this.props.readonly && this.activeActions.edit && res.controlPanel) {
            const initialEditable = this.editable || 'bottom';
            const initialMultiEdit = this.archInfo.multiEdit || false;
            const modeEntries = [
                { mode: 'read', name: _t('Open Form View'), icon: 'fa fa-external-link' },
                { mode: 'edit', name: _t('Inline Edit Mode'), icon: 'fa fa-pencil' },
            ];
            const setMode = (mode) => {
                this.editable = (
                    mode === 'edit' ? initialEditable : false
                );
                this.model.multiEdit = (
                    mode === 'edit' ? true : initialMultiEdit
                );
                browser.localStorage.setItem(
                    this.getModeStorageKey(), mode
                );
                this.model.notify();
            };
            res.controlPanel.modeSwitch = {
                currentMode: modeEntries.find((e) => (
                    e.mode === (this.editable ? 'edit' : 'read')
                )),
                modeSwitcherEntries: modeEntries.map((entry) => ({
                    ...entry,
                    onSelected: () => setMode(entry.mode),
                })),
            };
        }
        return res;
    },
});
