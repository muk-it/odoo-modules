import { Popup } from '@website/interactions/popup/popup';
import { registry } from '@web/core/registry';

import { browser } from '@web/core/browser/browser';
import { cookie } from '@web/core/browser/cookie';
import { getTabableElements } from '@web/core/utils/ui';

import {
    ESSENTIAL,
    allOptionalGranted,
    buildConsentState,
    matchStoredCookies,
} from '@muk_website_cookies_consent/interactions/cookies_banner/consent_state';

const CONSENT_COOKIE = 'muk_cookie_consent';
const CORE_COOKIE = 'website_cookies_bar';

/**
 * The consent banner and its preference centre.
 *
 * Replaces core's CookiesBar, which patches the gtag script at runtime and
 * injects the policy link from JS; both are rendered server-side here. Every
 * decision reloads the page, since scripts that already ran cannot be
 * unloaded and a withdrawal has to actually take effect. `dynamicContent`
 * spreads the parent's first, because a subclass field replaces it rather than
 * merging, and the two no-op handlers keep Popup from dismissing a dialog that
 * nothing but a decision may close.
 */
export class CookiesBanner extends Popup {
    static selector = '#website_cookies_bar';
    dynamicSelectors = {
        ...this.dynamicSelectors,
        _cookiesbus: () => this.services.website_cookies.bus,
    };
    dynamicContent = {
        ...this.dynamicContent,
        _cookiesbus: {
            't-on-cookiesBar.show': this.onReopenRequest,
            't-on-cookiesBar.toggle': this.onReopenRequest,
        },
        '.mk_cookies_accept_all': { 't-on-click': this.onAcceptAllClick },
        '.mk_cookies_reject_all': { 't-on-click': this.onRejectAllClick },
        '#muk_cookies_customize': { 't-on-click': this.onCustomiseClick },
        '#muk_cookies_dismiss': { 't-on-click': this.onDismissClick },
        '#muk_cookies_back': { 't-on-click': this.onBackClick },
        '#muk_cookies_save': { 't-on-click': this.onSaveClick },
        _document: { 't-on-click': this.onDocumentClick },
        '.modal': {
            't-on-keydown.capture': this.onModalKeydown,
        },
        '.js_close_popup': { 't-on-click': () => {} },
        '.btn-primary': { 't-on-click': () => {} },
    };
    setup() {
        super.setup();
        this.noticeEl = this.el.querySelector("[data-layer='notice']");
        this.preferencesEl = this.el.querySelector("[data-layer='preferences']");
        this.dismissEl = this.el.querySelector('#muk_cookies_dismiss');
        this.reopenerEl = null;
        this.removeFocusTrap = null;
        this.popupAlreadyShown = this.el.dataset.mukCookieAsk !== '1';
    }
    getSelectedCategories() {
        const inputEls = this.el.querySelectorAll("input[name='muk_cookie_category']");
        const codes = [...inputEls].filter((el) => el.checked).map((el) => el.value);
        return codes.includes(ESSENTIAL) ? codes : [ESSENTIAL, ...codes];
    }
    getAllCategories() {
        const inputEls = this.el.querySelectorAll("input[name='muk_cookie_category']");
        return [...inputEls].map((el) => el.value);
    }
    /**
     * Return the services granted by a set of purposes.
     *
     * Services asked for in place are excluded: accepting a purpose in the
     * dialog must not silently enable an embed the visitor never saw. So are
     * services under the strictly necessary purpose, such as the captcha that
     * lets a form be submitted at all: they run whatever the visitor decides,
     * and recording them as granted would make a withdrawal read as a grant.
     *
     * @param {string[]} categories
     * @returns {string[]}
     */
    getServicesFor(categories) {
        const serviceEls = this.el.querySelectorAll('[data-muk-service]');
        return [...serviceEls]
            .filter(
                (el) =>
                    el.dataset.mukContextual !== '1' &&
                    el.dataset.mukCategory !== ESSENTIAL &&
                    categories.includes(el.dataset.mukCategory),
            )
            .map((el) => el.dataset.mukService);
    }
    /**
     * Persist a decision, tell the rest of the page, record it, and reload.
     *
     * The value is percent-encoded, since a cookie carrying raw quotes and
     * commas is not reliably parsed server-side. Core's own cookie is written
     * in lockstep so untouched parts of Odoo keep gating correctly, and can
     * only claim full optional consent when nothing was refused. Nothing is
     * carried forward while the server is asking again, because the stored
     * payload has been invalidated — by a new policy version, a changed
     * registry or age — and reusing its grants would put back exactly what the
     * invalidation withdrew. An embed allowed in place answers nothing that was
     * asked, so it leaves `ans` clear unless an earlier answer still stands.
     *
     * @param {string[]} categories granted purpose codes
     * @param {string} action one of accept_all, reject_all, custom, withdraw
     * @param {string} source where the decision was made
     * @param {string[]} [extraServices] services granted individually, in place
     */
    applyDecision(categories, action, source, extraServices = []) {
        const data = this.el.dataset;
        const state = buildConsentState({
            categories,
            action,
            source,
            previous: this.isAsking() ? null : this.readState(),
            purposeServices: this.getServicesFor(categories),
            extraServices,
            contextualNames: this.getContextualServiceNames(),
            disclosure: {
                pv: data.mukCookiePv,
                rh: data.mukCookieRh,
                lang: data.mukCookieLang,
            },
            now: Math.floor(Date.now() / 1000),
            uid: this.readState()?.uid || this.newConsentUid(),
        });
        const maxAge = parseInt(data.mukCookieDays || '180') * 24 * 60 * 60;
        cookie.set(
            CONSENT_COOKIE,
            encodeURIComponent(JSON.stringify(state)),
            maxAge,
            'required',
        );
        const optional = allOptionalGranted(this.getAllCategories(), categories);
        cookie.set(
            CORE_COOKIE,
            `{"required": true, "optional": ${optional}, "ts": ${Date.now()}}`,
            maxAge,
            'required',
        );
        document.dispatchEvent(
            new Event(optional ? 'optionalCookiesAccepted' : 'optionalCookiesDenied'),
        );
        this.clearRefusedCookies(categories);
        this.recordDecision(state, action, source);
        this.bsModal.hide();
        browser.location.reload();
    }
    /**
     * Delete the declared cookies of every purpose that was not granted.
     *
     * Refusing has to take something away, not just stop adding to it. Only
     * declared names are touched, so nothing outside the disclosure is
     * removed; third-party cookies on another domain are beyond a page's reach.
     *
     * @param {string[]} categories the granted purpose codes
     */
    clearRefusedCookies(categories) {
        const declarationEls = this.el.querySelectorAll('[data-muk-cookie-name]');
        for (const el of declarationEls) {
            if (categories.includes(el.dataset.mukCookieOf)) {
                continue;
            }
            const pattern = el.dataset.mukCookiePattern;
            const names = pattern
                ? matchStoredCookies(document.cookie, pattern)
                : [el.dataset.mukCookieName];
            for (const name of names) {
                this.deleteCookieEverywhere(name);
            }
        }
    }
    /**
     * Expire a cookie for this host and for each domain it could be scoped to.
     *
     * A host-only expiry leaves a cookie set with an explicit Domain in place,
     * which is exactly how the analytics cookies worth clearing are written.
     *
     * @param {string} name
     */
    deleteCookieEverywhere(name) {
        cookie.delete(name);
        const parts = window.location.hostname.split('.');
        for (let i = 0; i < parts.length - 1; i++) {
            const domain = parts.slice(i).join('.');
            document.cookie = `${name}=;path=/;domain=${domain};max-age=0`;
            document.cookie = `${name}=;path=/;domain=.${domain};max-age=0`;
        }
    }
    /**
     * Return the cookie names currently set that match a declared pattern.
     *
     * Anchored, so a loose declaration cannot reach past its own purpose.
     *
     * @param {string} pattern a regular expression from a declaration
     * @returns {string[]}
     */
    getContextualServiceNames() {
        return [...this.el.querySelectorAll('[data-muk-contextual="1"]')].map(
            (el) => el.dataset.mukService,
        );
    }
    /**
     * Return whether the server is still asking, so nothing stored is in force.
     *
     * @returns {boolean}
     */
    isAsking() {
        return this.el.dataset.mukCookieAsk === '1';
    }
    currentCategories() {
        const state = this.isAsking() ? null : this.readState();
        const codes = state?.cats || [ESSENTIAL];
        return codes.includes(ESSENTIAL) ? codes : [ESSENTIAL, ...codes];
    }
    /**
     * Grant one blocked embed without touching any other choice.
     *
     * A visitor who clicks a blocked video wants that video, not a whole
     * purpose. Only that service is granted; the purposes stay exactly as
     * they were, and the banner still asks its own question afterwards.
     *
     * @param {HTMLElement} allowEl the control naming the service to allow
     */
    allowEmbed(allowEl) {
        const service = allowEl.dataset.mukCookieService;
        if (!service) {
            return false;
        }
        this.applyDecision(this.currentCategories(), 'custom', 'embed', [service]);
        return true;
    }
    /**
     * Return a fresh consent reference, random so it identifies nothing else.
     *
     * @returns {string}
     */
    newConsentUid() {
        if (window.crypto?.randomUUID) {
            return window.crypto.randomUUID();
        }
        return `${Date.now().toString(36)}-${Math.floor(Math.random() * 1e12).toString(
            36,
        )}`;
    }
    readState() {
        try {
            return JSON.parse(decodeURIComponent(cookie.get(CONSENT_COOKIE) || 'null'));
        } catch {
            return null;
        }
    }
    /**
     * Send the decision to the server as proof, without delaying the reload.
     *
     * Sent with keepalive so the request survives the navigation that follows.
     * A failure here must never cost the visitor their choice, which is
     * already stored in the cookie by this point, so errors are swallowed.
     *
     * @param {object} state the payload written to the consent cookie
     * @param {string} action
     * @param {string} source
     */
    recordDecision(state, action, source) {
        if (this.el.dataset.mukCookieLog !== '1') {
            return;
        }
        const payload = {
            id: 1,
            jsonrpc: '2.0',
            method: 'call',
            params: { state: state, action: action, source: source },
        };
        try {
            browser
                .fetch('/muk_website_cookies_consent/consent', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                    keepalive: true,
                })
                .catch(() => {});
        } catch {
            return;
        }
    }
    /**
     * Leave the page usable, and the visitor's focus alone, while asking.
     *
     * Popup takes focus and Bootstrap stamps `aria-modal` on whatever it
     * shows. Neither is true of the notice, which has no backdrop and leaves
     * the page usable behind it; the preference centre claims both instead.
     */
    trapFocus() {
        if (!this.modalEl?.classList.contains('mk_cookies_expanded')) {
            this.modalEl?.removeAttribute('aria-modal');
        }
    }
    /**
     * Open the detail layer, which covers the page and so is genuinely modal.
     */
    showPreferences() {
        this.noticeEl?.classList.add('d-none');
        this.preferencesEl?.classList.remove('d-none');
        this.modalEl?.classList.add('mk_cookies_expanded');
        this.modalEl?.setAttribute('aria-labelledby', 'muk_cookies_prefs_title');
        this.modalEl?.setAttribute('aria-modal', 'true');
        this.lockPage();
        this.installFocusTrap();
        this.focusFirstControl();
    }
    /**
     * Stop the page scrolling behind a layer that claims to block it.
     *
     * Hiding the root scroller's overflow would lock the page but clamp it to
     * the top, so a visitor who opened this mid-page would be returned to the
     * top of it. Offsetting a fixed body by the scroll it had holds the page
     * exactly where they left it, and it is the offset that is put back.
     */
    lockPage() {
        if (document.body.classList.contains('mk_cookies_locked')) {
            return;
        }
        this.lockedScroll = window.scrollY;
        document.body.style.top = `-${this.lockedScroll}px`;
        document.body.classList.add('mk_cookies_locked');
    }
    unlockPage() {
        if (!document.body.classList.contains('mk_cookies_locked')) {
            return;
        }
        document.body.classList.remove('mk_cookies_locked');
        document.body.style.top = '';
        window.scrollTo(0, this.lockedScroll ?? 0);
    }
    showNotice() {
        this.preferencesEl?.classList.add('d-none');
        this.noticeEl?.classList.remove('d-none');
        this.modalEl?.classList.remove('mk_cookies_expanded');
        this.modalEl?.setAttribute('aria-labelledby', 'muk_cookies_title');
        this.modalEl?.removeAttribute('aria-modal');
        this.unlockPage();
        this.releaseFocusTrap();
    }
    leavePreferences() {
        this.showNotice();
        this.el.querySelector('#muk_cookies_customize')?.focus();
    }
    /**
     * Keep Tab inside the expanded layer, listening on the document.
     *
     * A trap that only hears keys inside the dialog goes silent the moment
     * focus is somewhere else, which is exactly when it is needed.
     */
    installFocusTrap() {
        this.releaseFocusTrap();
        this.removeFocusTrap = this.addListener(
            document,
            'keydown',
            this.onTrappedKeydown,
        );
    }
    releaseFocusTrap() {
        this.removeFocusTrap?.();
        this.removeFocusTrap = null;
    }
    /**
     * Show the notice again, moving focus into it rather than leaving the
     * visitor on the control they pressed.
     *
     * The listener goes on before the dialog is shown: this modal does not
     * fade, so Bootstrap fires `shown` synchronously inside `show()` and a
     * listener added afterwards never runs. A dialog that is already open
     * fires nothing at all, so that case moves focus directly.
     */
    reopen() {
        this.popupAlreadyShown = false;
        this.showNotice();
        this.dismissEl?.classList.toggle('d-none', !this.canDismiss());
        if (this.modalEl?.classList.contains('show')) {
            this.focusFirstControl();
            return;
        }
        this.addListener(
            this.modalEl,
            'shown.bs.modal',
            () => this.focusFirstControl(),
            { once: true },
        );
        this.bsModal.show();
    }
    focusFirstControl() {
        const layerEl = this.preferencesEl?.classList.contains('d-none')
            ? this.noticeEl
            : this.preferencesEl;
        layerEl?.querySelector('button, input:not([disabled])')?.focus();
    }
    /**
     * Return whether closing the banner may leave the visitor's choice alone.
     *
     * A first visit has to be answered, which is why the notice offers no way
     * out but a decision. Once a decision is in force, reopening it is the
     * visitor looking, and looking must not cost them their choice: the only
     * other ways out of the reopened banner both write a new one, and refusing
     * would silently withdraw what they came to check.
     *
     * @returns {boolean}
     */
    canDismiss() {
        return !this.isAsking() && !!this.readState();
    }
    /**
     * Close the reopened banner, leaving the decision in force untouched.
     */
    dismiss() {
        if (!this.canDismiss()) {
            return;
        }
        this.showNotice();
        this.dismissEl?.classList.add('d-none');
        this.popupAlreadyShown = true;
        this.bsModal?.hide();
        if (this.reopenerEl?.isConnected) {
            this.reopenerEl.focus();
        }
    }
    onAcceptAllClick(ev) {
        ev.preventDefault();
        this.applyDecision(this.getAllCategories(), 'accept_all', this.getSource());
    }
    onRejectAllClick(ev) {
        ev.preventDefault();
        const action = this.readState() ? 'withdraw' : 'reject_all';
        this.applyDecision([ESSENTIAL], action, this.getSource());
    }
    onSaveClick(ev) {
        ev.preventDefault();
        const selected = this.getSelectedCategories();
        const optionalCount = this.getAllCategories().filter(
            (code) => code !== ESSENTIAL,
        ).length;
        let action = 'custom';
        if (selected.length === optionalCount + 1) {
            action = 'accept_all';
        } else if (selected.length === 1) {
            action = this.readState() ? 'withdraw' : 'reject_all';
        }
        this.applyDecision(selected, action, 'preferences');
    }
    onCustomiseClick(ev) {
        ev.preventDefault();
        this.showPreferences();
    }
    onBackClick(ev) {
        ev.preventDefault();
        this.leavePreferences();
    }
    onDismissClick(ev) {
        ev.preventDefault();
        this.dismiss();
    }
    /**
     * Return which layer the decision was taken on.
     *
     * @returns {string}
     */
    getSource() {
        return this.preferencesEl?.classList.contains('d-none')
            ? 'banner'
            : 'preferences';
    }
    onReopenRequest() {
        this.reopen();
    }
    /**
     * Reopen the banner from any control placed outside it.
     *
     * @param {MouseEvent} ev
     */
    onDocumentClick(ev) {
        const allowEl = ev.target.closest('.mk_cookies_allow_embed');
        if (allowEl) {
            ev.preventDefault();
            ev.stopPropagation();
            this.allowEmbed(allowEl);
            return;
        }
        const reopenEl = ev.target.closest('.mk_cookies_reopen');
        if (reopenEl) {
            ev.preventDefault();
            this.reopenerEl = reopenEl;
            this.reopen();
        }
    }
    /**
     * Wrap Tab and Shift+Tab around the controls of the open layer.
     *
     * Recomputed on every press: the tabbable set grows and shrinks as the
     * visitor opens the cookie tables inside the layer.
     *
     * @param {KeyboardEvent} ev
     */
    onTrappedKeydown(ev) {
        if (ev.key !== 'Tab') {
            return;
        }
        const tabableEls = getTabableElements(this.modalEl);
        if (!tabableEls.length) {
            return;
        }
        const firstEl = tabableEls[0];
        const lastEl = tabableEls[tabableEls.length - 1];
        if (!this.modalEl.contains(ev.target)) {
            ev.preventDefault();
            (ev.shiftKey ? lastEl : firstEl).focus();
        } else if (!ev.shiftKey && ev.target === lastEl) {
            ev.preventDefault();
            firstEl.focus();
        } else if (ev.shiftKey && ev.target === firstEl) {
            ev.preventDefault();
            lastEl.focus();
        }
    }
    /**
     * Let Escape leave the layer it opened, and nothing more.
     *
     * A dismissal must not imply consent, and it must not imply a refusal
     * either. Refuse all is the documented way out of a banner that is still
     * asking, which is why it sits on the first layer with the same weight as
     * accept. Once a decision is in force there is nothing left to answer, so
     * Escape closes the banner and leaves that decision exactly as it was.
     *
     * @param {KeyboardEvent} ev
     */
    onModalKeydown(ev) {
        if (ev.key !== 'Escape') {
            return;
        }
        ev.stopImmediatePropagation();
        ev.preventDefault();
        if (this.modalEl?.classList.contains('mk_cookies_expanded')) {
            this.leavePreferences();
            return;
        }
        this.dismiss();
    }
    /**
     * Never persist anything when the dialog closes on its own.
     *
     * Popup writes its cookie on hide. Consent is only ever written by an
     * explicit decision, so this override deliberately does nothing.
     */
    onHideModal() {}
}

registry
    .category('public.interactions')
    .add('website.cookies_bar', CookiesBanner, { force: true });
