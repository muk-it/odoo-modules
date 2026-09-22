import { browser } from '@web/core/browser/browser';
import { _t } from '@web/core/l10n/translation';
import { useBus } from '@web/core/utils/hooks';
import { patch } from '@web/core/utils/patch';
import { ControlPanel } from '@web/search/control_panel/control_panel';

import { onWillDestroy, proxy, useListener, useOnChange } from '@odoo/owl';

import { getAutoLoadInterval } from '@muk_web_refresh/core/utils/refresh';
import { REFRESH_VIEW_EVENT } from '@muk_web_refresh/services/refresh/refresh_plugin';

/**
 * Provide a callback that briefly flashes the refresh animation on the content.
 *
 * @param {number} timeout how long the animation class stays on, in ms
 * @returns {Function} a callback that starts the animation
 */
function useRefreshAnimation(timeout) {
    let timeoutId = null;
    function contentClassList() {
        const content = document.querySelector('.o_content');
        return content ? content.classList : null;
    }
    function clearAnimationTimeout() {
        if (timeoutId) {
            clearTimeout(timeoutId);
        }
        timeoutId = null;
    }
    function animate() {
        clearAnimationTimeout();
        const classList = contentClassList();
        if (classList) {
            classList.add('mk_refresh');
            timeoutId = setTimeout(() => {
                classList.remove('mk_refresh');
                clearAnimationTimeout();
            }, timeout);
        }
    }
    onWillDestroy(clearAnimationTimeout);
    return animate;
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
                this.checkAutoLoadAvailability() && !!this.getAutoLoadStorageValue(),
            counter: 0,
        });
        this.visibilityState = proxy({ hidden: document.hidden });
        useListener(document, 'visibilitychange', () => {
            this.visibilityState.hidden = document.hidden;
        });
        onWillDestroy(() => {
            if (this._clickTimeout) {
                clearTimeout(this._clickTimeout);
            }
        });
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
        const keys = [
            this.env?.config?.actionId ?? '',
            this.env?.config?.viewType ?? '',
            this.env?.config?.viewId ?? '',
        ];
        return `pager_autoload:${keys.join(',')}`;
    },
    /**
     * Read the stored auto-load toggle for the open action and view.
     *
     * @returns {string|null} the stored value, or null when unset
     */
    getAutoLoadStorageValue() {
        return browser.localStorage.getItem(this.getAutoLoadStorageKey());
    },
    /** Remember that auto-load is on for the open action and view. */
    setAutoLoadStorageValue() {
        browser.localStorage.setItem(this.getAutoLoadStorageKey(), true);
    },
    /** Forget the auto-load toggle for the open action and view. */
    removeAutoLoadStorageValue() {
        browser.localStorage.removeItem(this.getAutoLoadStorageKey());
    },
    /** Flip auto-load for the open view and persist the new state. */
    toggleAutoLoad() {
        this.autoLoadState.active = !this.autoLoadState.active;
        if (this.autoLoadState.active) {
            this.setAutoLoadStorageValue();
        } else {
            this.removeAutoLoadStorageValue();
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
        if (this._clickTimeout) {
            clearTimeout(this._clickTimeout);
            this._clickTimeout = null;
        }
        this._clickTimeout = setTimeout(async () => {
            this._clickTimeout = null;
            if (await this.refreshView()) {
                this.refreshAnimation();
            }
        }, 300);
    },
    onDblClickRefresh() {
        if (this._clickTimeout) {
            clearTimeout(this._clickTimeout);
            this._clickTimeout = null;
        }
        if (this.checkAutoLoadAvailability()) {
            this.toggleAutoLoad();
        }
    },
});
