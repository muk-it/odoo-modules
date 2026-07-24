import { Component, onWillStart, useState } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { useHotkey } from '@web/core/hotkeys/hotkey_hook';
import { useAutofocus } from '@web/core/utils/hooks';
import { KeepLast } from '@web/core/utils/concurrency';
import { debounce } from '@web/core/utils/timing';

import { Dialog } from '@web/core/dialog/dialog';

/**
 * Search dialog to pick a mail canned response for insertion into the html
 * editor. Records are fetched through the `search` prop and the chosen record
 * is passed back through the `select` prop.
 */
export class CannedResponseDialog extends Component {
    static template = 'muk_mail_utils.CannedResponseDialog';
    static components = { Dialog };
    static props = {
        close: Function,
        search: Function,
        select: Function,
    };

    setup() {
        this.state = useState({
            records: [],
            selectedIndex: 0,
        });
        this.searchInput = useAutofocus();
        this.keepLast = new KeepLast();
        this.debouncedSearch = debounce((searchValue) => this.search(searchValue), 250);
        useHotkey('ArrowDown', () => this.navigate(1), {
            allowRepeat: true,
            bypassEditableProtection: true,
        });
        useHotkey('ArrowUp', () => this.navigate(-1), {
            allowRepeat: true,
            bypassEditableProtection: true,
        });
        useHotkey('Enter', () => this.selectCurrent(), {
            bypassEditableProtection: true,
        });
        onWillStart(() => this.search(''));
    }

    get title() {
        return _t('Canned Responses');
    }

    /**
     * Fetches the canned responses matching the given term. Results of a
     * superseded search are dropped, so a slow response cannot overwrite
     * the list of a newer one.
     * @param {string} searchValue
     */
    async search(searchValue) {
        this.state.records = await this.keepLast.add(this.props.search(searchValue));
        this.state.selectedIndex = 0;
    }

    /**
     * Moves the keyboard selection up or down (with wrap around).
     * @param {number} step
     */
    navigate(step) {
        const count = this.state.records.length;
        if (count) {
            this.state.selectedIndex =
                (this.state.selectedIndex + step + count) % count;
        }
    }

    /** Confirms the currently highlighted canned response. */
    selectCurrent() {
        const record = this.state.records[this.state.selectedIndex];
        if (record) {
            this.props.select(record);
            this.props.close();
        }
    }

    onSearchInput(ev) {
        this.debouncedSearch(ev.target.value);
    }

    onRecordClick(index) {
        this.state.selectedIndex = index;
        this.selectCurrent();
    }

    onRecordMouseEnter(index) {
        this.state.selectedIndex = index;
    }
}
