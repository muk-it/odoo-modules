import { browser } from '@web/core/browser/browser';
import { patch } from '@web/core/utils/patch';
import { useService } from '@web/core/utils/hooks';
import { session } from '@web/session';

import { ControlPanel } from '@web/search/control_panel/control_panel';

import { useState, onWillDestroy, useEffect } from '@odoo/owl';

const DBLCLICK_DELAY = 300;

function useRefreshAnimation(timeout) {
    const refreshClass = 'o_content__refresh';
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
            classList.add(refreshClass);
            timeoutId = setTimeout(() => {
                classList.remove(refreshClass);
                clearAnimationTimeout();
            }, timeout);
        }
    }
    return animate;
}

patch(ControlPanel.prototype, {
    setup() {
        super.setup();
        this.action = useService('action');
        this.refreshAnimation = useRefreshAnimation(600);
        this._clickTimeout = null;
        this.autoLoadState = useState({
            active: (
                this.checkAutoLoadAvailability() &&
                !!this.getAutoLoadStorageValue()
            ),
            counter: 0,
        });
        onWillDestroy(() => {
            if (this._clickTimeout) {
                clearTimeout(this._clickTimeout);
            }
        });
        useEffect(
            () => {
                if (!this.autoLoadState.active) {
                    return;
                }
                this.autoLoadState.counter = (
                    this.getAutoLoadRefreshInterval()
                );
                const interval = browser.setInterval(
                    () => {
                        this.autoLoadState.counter = (
                            this.autoLoadState.counter ?
                            this.autoLoadState.counter - 1 :
                            this.getAutoLoadRefreshInterval()
                        );
                        if (this.autoLoadState.counter <= 0) {
                            this.autoLoadState.counter = (
                                this.getAutoLoadRefreshInterval()
                            );
                            this.refreshView();
                        }
                    },
                    1000
                );
                return () => browser.clearInterval(interval);
            },
            () => [this.autoLoadState.active]
        );
    },
    checkAutoLoadAvailability() {
        return ['kanban', 'list'].includes(this.env.config.viewType);
    },
    checkRefreshAvailability() {
        const forbiddenSubType = ['base_settings'];
        return !forbiddenSubType.includes(this.env.config.viewSubType);
    },
    getAutoLoadRefreshInterval() {
        return (session.pager_autoload_interval ?? 30000) / 1000;
    },
    getAutoLoadStorageKey() {
        const keys = [
            this.env?.config?.actionId ?? '',
            this.env?.config?.viewType ?? '',
            this.env?.config?.viewId ?? '',
        ];
        return `pager_autoload:${keys.join(',')}`;
    },
    getAutoLoadStorageValue() {
        return browser.localStorage.getItem(
            this.getAutoLoadStorageKey()
        );
    },
    setAutoLoadStorageValue() {
        browser.localStorage.setItem(
            this.getAutoLoadStorageKey(), true
        );
    },
    removeAutoLoadStorageValue() {
        browser.localStorage.removeItem(
            this.getAutoLoadStorageKey()
        );
    },
    toggleAutoLoad() {
        this.autoLoadState.active = (
            !this.autoLoadState.active
        );
        if (this.autoLoadState.active) {
            this.setAutoLoadStorageValue();
        } else {
            this.removeAutoLoadStorageValue();
        }
    },
    async refreshView() {
        if (this.pagerProps?.onUpdate) {
            await this.pagerProps.onUpdate({
                offset: this.pagerProps.offset,
                limit: this.pagerProps.limit,
            });
            return true;
        }
        if (
            this.env.searchModel &&
            typeof this.env.searchModel.search === 'function'
        ) {
            this.env.searchModel.search();
            return true;
        }
        return false;
    },
    async refreshReport() {
        const viewAction = this.action.currentController.action;
        const options = {};
        if (this.env.config.breadcrumbs.length > 1) {
            const breadcrumb = this.env.config.breadcrumbs.slice(-1);
            await this.action.restore(breadcrumb.jsId);
        } else {
            options.clearBreadcrumbs = true;
        }
        this.action.doAction(viewAction, options);
    },
    onClickRefresh() {
        if (this._clickTimeout) {
            clearTimeout(this._clickTimeout);
            this._clickTimeout = null;
        }
        this._clickTimeout = setTimeout(async () => {
            this._clickTimeout = null;
            if (!this.env.searchModel && !this.pagerProps) {
                return this.refreshReport();
            }
            const updated = await this.refreshView();
            if (updated) {
                this.refreshAnimation();
            }
        }, DBLCLICK_DELAY);
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
