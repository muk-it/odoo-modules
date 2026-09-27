import { browser } from '@web/core/browser/browser';
import { _t } from '@web/core/l10n/translation';
import { useBus } from '@web/core/utils/hooks';
import { patch } from '@web/core/utils/patch';
import { ControlPanel } from '@web/search/control_panel/control_panel';

import { onWillDestroy, proxy, useListener, useOnChange } from '@odoo/owl';

import {
    getAutoLoadInterval,
    REFRESH_VIEW_EVENT,
} from '@muk_web_refresh/services/refresh/refresh_plugin';

/**
 * Provide a callback that briefly flashes the refresh animation on the content.
 *
 * @param {number} timeout how long the animation class stays on, in ms
 * @returns {Function} a callback that starts the animation
 */
function useRefreshAnimation(timeout) {
    let timeoutId = null;
    onWillDestroy(() => clearTimeout(timeoutId));
    return () => {
        const content = document.querySelector('.o_content');
        if (content) {
            clearTimeout(timeoutId);
            content.classList.add('mk_refresh');
            timeoutId = setTimeout(
                () => content.classList.remove('mk_refresh'),
                timeout,
            );
        }
    };
}

/** Add a manual refresh button and a per-view auto-load timer. */
patch(ControlPanel.prototype, {
    setup() {
        super.setup();
        this._clickTimeout = null;
        this._refreshInFlight = false;
        this.refreshAnimation = useRefreshAnimation(600);
        useBus(this.env.bus, REFRESH_VIEW_EVENT, () => {
            this.refreshView();
        });
        this.autoLoadState = proxy({
            active:
                this.checkAutoLoadAvailability() &&
                !!browser.localStorage.getItem(this.getAutoLoadStorageKey()),
            counter: 0,
        });
        this.visibilityState = proxy({ hidden: document.hidden });
        useListener(document, 'visibilitychange', () => {
            this.visibilityState.hidden = document.hidden;
        });
        onWillDestroy(() => clearTimeout(this._clickTimeout));
        useOnChange(
            () => [this.autoLoadState.active, this.visibilityState.hidden],
            (active, hidden) => {
                if (!active || hidden) {
                    return;
                }
                this.autoLoadState.counter = this.getAutoLoadRefreshInterval();
                const interval = browser.setInterval(() => {
                    this.autoLoadState.counter = this.autoLoadState.counter
                        ? this.autoLoadState.counter - 1
                        : this.getAutoLoadRefreshInterval();
                    if (this.autoLoadState.counter <= 0) {
                        this.autoLoadState.counter = this.getAutoLoadRefreshInterval();
                        if (!this._refreshInFlight) {
                            this._refreshInFlight = true;
                            this.refreshView().finally(() => {
                                this._refreshInFlight = false;
                            });
                        }
                    }
                }, 1000);
                return () => browser.clearInterval(interval);
            },
            { initialRun: true },
        );
    },
    get refreshTitle() {
        return this.autoLoadState.active
            ? _t('Auto Refresh Active (Double-Click to Disable)')
            : _t('Refresh (Double-Click for Auto Refresh)');
    },
    /**
     * Tell whether the current view can run the auto-load timer.
     *
     * @returns {boolean} true on a list or kanban view
     */
    checkAutoLoadAvailability() {
        return ['kanban', 'list'].includes(this.env.config.viewType);
    },
    /**
     * Tell whether the refresh button belongs on the current view.
     *
     * @returns {boolean} true on every view but the settings form
     */
    checkRefreshAvailability() {
        return !['base_settings'].includes(this.env.config.viewSubType);
    },
    /**
     * Return the configured auto-load interval as a countdown value.
     *
     * @returns {number} the interval in seconds
     */
    getAutoLoadRefreshInterval() {
        return getAutoLoadInterval() / 1000;
    },
    /**
     * Build the per-action localStorage key tracking the auto-load toggle.
     *
     * @returns {string} the storage key for the open action and view
     */
    getAutoLoadStorageKey() {
        const { actionId, viewType, viewId } = this.env.config;
        return `pager_autoload:${[actionId, viewType, viewId].join(',')}`;
    },
    /** Flip auto-load for the open view and persist the new state. */
    toggleAutoLoad() {
        this.autoLoadState.active = !this.autoLoadState.active;
        const key = this.getAutoLoadStorageKey();
        if (this.autoLoadState.active) {
            browser.localStorage.setItem(key, true);
        } else {
            browser.localStorage.removeItem(key);
        }
    },
    /**
     * Reload the current view through the pager or the search model.
     *
     * @returns {Promise<boolean>} true when a reload was issued
     */
    async refreshView() {
        if (this.pagerProps?.onUpdate) {
            await this.pagerProps.onUpdate({
                offset: this.pagerProps.offset,
                limit: this.pagerProps.limit,
            });
            return true;
        }
        if (typeof this.env.searchModel?.search === 'function') {
            this.env.searchModel.search();
            return true;
        }
        return false;
    },
    onClickRefresh() {
        clearTimeout(this._clickTimeout);
        this._clickTimeout = setTimeout(async () => {
            if (await this.refreshView()) {
                this.refreshAnimation();
            }
        }, 300);
    },
    onDblClickRefresh() {
        clearTimeout(this._clickTimeout);
        if (this.checkAutoLoadAvailability()) {
            this.toggleAutoLoad();
        }
    },
});
