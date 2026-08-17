/** @odoo-module **/

import publicWidget from '@web/legacy/js/public/public_widget';
import PopupWidget from '@website/snippets/s_popup/000';

import { browser } from '@web/core/browser/browser';
import { cookie } from '@web/core/browser/cookie';
import { getTabableElements } from '@web/core/utils/ui';

import {
    ESSENTIAL,
    allOptionalGranted,
    buildConsentState,
    matchStoredCookies,
} from '@muk_website_cookies_consent/snippets/cookies_banner/consent_state';

const CONSENT_COOKIE = 'muk_cookie_consent';
const CORE_COOKIE = 'website_cookies_bar';

/**
 * The consent banner and its preference centre.
 *
 * Replaces core's cookies bar, which patches the gtag script at runtime and
 * injects the policy link from JS; both are rendered server-side here. Every
 * decision reloads the page, since scripts that already ran cannot be unloaded
 * and a withdrawal has to actually take effect. The popup widget is extended
 * rather than rewritten so the modal plumbing keeps behaving as core expects,
 * and only the consent logic is replaced.
 */
const CookiesBanner = PopupWidget.extend({
    selector: '#website_cookies_bar',
    events: Object.assign({}, PopupWidget.prototype.events, {
        'click .mk_cookies_accept_all': '_onAcceptAllClick',
        'click .mk_cookies_reject_all': '_onRejectAllClick',
        'click #muk_cookies_customize': '_onCustomiseClick',
        'click #muk_cookies_dismiss': '_onDismissClick',
        'click #muk_cookies_back': '_onBackClick',
        'click #muk_cookies_save': '_onSaveClick',
        show_cookies_bar: '_onShowCookiesBar',
    }),

    /**
     * @override
     */
    start() {
        this.noticeEl = this.el.querySelector("[data-layer='notice']");
        this.preferencesEl = this.el.querySelector("[data-layer='preferences']");
        this.dismissEl = this.el.querySelector('#muk_cookies_dismiss');
        this.modalEl = this.el.querySelector('.modal');
        this.reopenerEl = null;
        this.__onModalKeydown = this._onModalKeydown.bind(this);
        this.__onDocumentClick = this._onDocumentClick.bind(this);
        this.__onTrappedKeydown = this._onTrappedKeydown.bind(this);
        this.modalEl.addEventListener('keydown', this.__onModalKeydown, true);
        document.addEventListener('click', this.__onDocumentClick);
        const result = this._super(...arguments);
        // The server decides whether the question still stands; core's own
        // cookie, which the parent reads, only knows that something was once
        // answered and would keep the banner shut after a policy bump.
        clearTimeout(this.timeout);
        this._popupAlreadyShown = !this._isAsking();
        if (this._isAsking()) {
            this._bindPopup();
        }
        return result;
    },
    /**
     * @override
     */
    destroy() {
        this.modalEl.removeEventListener('keydown', this.__onModalKeydown, true);
        document.removeEventListener('click', this.__onDocumentClick);
        this._releaseFocusTrap();
        this._unlockPage();
        this._super(...arguments);
    },

    //--------------------------------------------------------------------------
    // Private
    //--------------------------------------------------------------------------

    /**
     * Return the purposes ticked in the preference centre.
     *
     * @private
     * @returns {string[]}
     */
    _getSelectedCategories() {
        const inputEls = this.el.querySelectorAll("input[name='muk_cookie_category']");
        const codes = [...inputEls].filter((el) => el.checked).map((el) => el.value);
        return codes.includes(ESSENTIAL) ? codes : [ESSENTIAL, ...codes];
    },
    /**
     * Return every purpose the dialog put to the visitor.
     *
     * @private
     * @returns {string[]}
     */
    _getAllCategories() {
        const inputEls = this.el.querySelectorAll("input[name='muk_cookie_category']");
        return [...inputEls].map((el) => el.value);
    },
    /**
     * Return the services granted by a set of purposes.
     *
     * Services asked for in place are excluded: accepting a purpose in the
     * dialog must not silently enable an embed the visitor never saw. So are
     * services under the strictly necessary purpose, such as the captcha that
     * lets a form be submitted at all: they run whatever the visitor decides,
     * and recording them as granted would make a withdrawal read as a grant.
     *
     * @private
     * @param {string[]} categories
     * @returns {string[]}
     */
    _getServicesFor(categories) {
        const serviceEls = this.el.querySelectorAll('[data-muk-service]');
        return [...serviceEls]
            .filter(
                (el) =>
                    el.dataset.mukContextual !== '1' &&
                    el.dataset.mukCategory !== ESSENTIAL &&
                    categories.includes(el.dataset.mukCategory),
            )
            .map((el) => el.dataset.mukService);
    },
    /**
     * Return the services that are only ever asked for on the embed itself.
     *
     * @private
     * @returns {string[]}
     */
    _getContextualServiceNames() {
        return [...this.el.querySelectorAll("[data-muk-contextual='1']")].map(
            (el) => el.dataset.mukService,
        );
    },
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
     * @private
     * @param {string[]} categories granted purpose codes
     * @param {string} action one of accept_all, reject_all, custom, withdraw
     * @param {string} source where the decision was made
     * @param {string[]} [extraServices] services granted individually, in place
     */
    _applyDecision(categories, action, source, extraServices = []) {
        const data = this.el.dataset;
        const state = buildConsentState({
            categories,
            action,
            source,
            previous: this._isAsking() ? null : this._readState(),
            purposeServices: this._getServicesFor(categories),
            extraServices,
            contextualNames: this._getContextualServiceNames(),
            disclosure: {
                pv: data.mukCookiePv,
                rh: data.mukCookieRh,
                lang: data.mukCookieLang,
            },
            now: Math.floor(Date.now() / 1000),
            uid: this._readState()?.uid || this._newConsentUid(),
        });
        const maxAge = parseInt(data.mukCookieDays || '180') * 24 * 60 * 60;
        cookie.set(
            CONSENT_COOKIE,
            encodeURIComponent(JSON.stringify(state)),
            maxAge,
            'required',
        );
        const optional = allOptionalGranted(this._getAllCategories(), categories);
        cookie.set(
            CORE_COOKIE,
            `{"required": true, "optional": ${optional}, "ts": ${Date.now()}}`,
            maxAge,
            'required',
        );
        document.dispatchEvent(
            new Event(optional ? 'optionalCookiesAccepted' : 'optionalCookiesDenied'),
        );
        this._clearRefusedCookies(categories);
        this._recordDecision(state, action, source);
        this._hidePopup();
        browser.location.reload();
    },
    /**
     * Delete the declared cookies of every purpose that was not granted.
     *
     * Refusing has to take something away, not just stop adding to it. Only
     * declared names are touched, so nothing outside the disclosure is
     * removed; third-party cookies on another domain are beyond a page's reach.
     *
     * @private
     * @param {string[]} categories the granted purpose codes
     */
    _clearRefusedCookies(categories) {
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
                this._deleteCookieEverywhere(name);
            }
        }
    },
    /**
     * Expire a cookie for this host and for each domain it could be scoped to.
     *
     * A host-only expiry leaves a cookie set with an explicit Domain in place,
     * which is exactly how the analytics cookies worth clearing are written.
     *
     * @private
     * @param {string} name
     */
    _deleteCookieEverywhere(name) {
        cookie.delete(name);
        const parts = window.location.hostname.split('.');
        for (let i = 0; i < parts.length - 1; i++) {
            const domain = parts.slice(i).join('.');
            document.cookie = `${name}=;path=/;domain=${domain};max-age=0`;
            document.cookie = `${name}=;path=/;domain=.${domain};max-age=0`;
        }
    },
    /**
     * Return whether the server is still asking, so nothing stored is in force.
     *
     * @private
     * @returns {boolean}
     */
    _isAsking() {
        return this.el.dataset.mukCookieAsk === '1';
    },
    /**
     * Return the purposes in force right now, essential always among them.
     *
     * @private
     * @returns {string[]}
     */
    _currentCategories() {
        const state = this._isAsking() ? null : this._readState();
        const codes = state?.cats || [ESSENTIAL];
        return codes.includes(ESSENTIAL) ? codes : [ESSENTIAL, ...codes];
    },
    /**
     * Grant one blocked embed without touching any other choice.
     *
     * A visitor who clicks a blocked video wants that video, not a whole
     * purpose. Only that service is granted; the purposes stay exactly as
     * they were, and the banner still asks its own question afterwards.
     *
     * @private
     * @param {HTMLElement} allowEl the control naming the service to allow
     * @returns {boolean}
     */
    _allowEmbed(allowEl) {
        const service = allowEl.dataset.mukCookieService;
        if (!service) {
            return false;
        }
        this._applyDecision(this._currentCategories(), 'custom', 'embed', [service]);
        return true;
    },
    /**
     * Return a fresh consent reference, random so it identifies nothing else.
     *
     * @private
     * @returns {string}
     */
    _newConsentUid() {
        if (window.crypto?.randomUUID) {
            return window.crypto.randomUUID();
        }
        return `${Date.now().toString(36)}-${Math.floor(Math.random() * 1e12).toString(
            36,
        )}`;
    },
    /**
     * Return the stored payload, or null when there is none to read.
     *
     * @private
     * @returns {object|null}
     */
    _readState() {
        try {
            return JSON.parse(decodeURIComponent(cookie.get(CONSENT_COOKIE) || 'null'));
        } catch {
            return null;
        }
    },
    /**
     * Send the decision to the server as proof, without delaying the reload.
     *
     * Sent with keepalive so the request survives the navigation that follows.
     * A failure here must never cost the visitor their choice, which is
     * already stored in the cookie by this point, so errors are swallowed.
     *
     * @private
     * @param {object} state the payload written to the consent cookie
     * @param {string} action
     * @param {string} source
     */
    _recordDecision(state, action, source) {
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
    },
    /**
     * Leave the page usable, and the visitor's focus alone, while asking.
     *
     * The parent moves focus into whatever it shows and Bootstrap stamps
     * `aria-modal` on it. Neither is true of the notice, which has no backdrop
     * and leaves the page usable behind it; the preference centre claims both
     * instead.
     *
     * @override
     */
    _trapFocus() {
        if (!this.modalEl.classList.contains('mk_cookies_expanded')) {
            this.modalEl.removeAttribute('aria-modal');
        }
        return () => {};
    },
    /**
     * Open the detail layer, which covers the page and so is genuinely modal.
     *
     * @private
     */
    _showPreferences() {
        this.noticeEl?.classList.add('d-none');
        this.preferencesEl?.classList.remove('d-none');
        this.modalEl.classList.add('mk_cookies_expanded');
        this.modalEl.setAttribute('aria-labelledby', 'muk_cookies_prefs_title');
        this.modalEl.setAttribute('aria-modal', 'true');
        this._lockPage();
        this._installFocusTrap();
        this._focusFirstControl();
    },
    /**
     * Return the element the page actually scrolls, or null for the window.
     *
     * This branch scrolls the layout wrapper rather than the document, and a
     * lock aimed at the wrong one either does nothing or throws the visitor
     * back to the top.
     *
     * @private
     * @returns {HTMLElement|null}
     */
    _getScrollerEl() {
        const wrapEl = document.getElementById('wrapwrap');
        const overflow = wrapEl && getComputedStyle(wrapEl).overflowY;
        return overflow === 'auto' || overflow === 'scroll' ? wrapEl : null;
    },
    /**
     * Stop the page scrolling behind a layer that claims to block it.
     *
     * An element that scrolls its own content keeps its position when its
     * overflow is hidden, so there the lock is that and nothing more. The
     * document scroller does not: hiding its overflow clamps it to the top, so
     * a visitor who opened this mid-page would be returned to the top of it.
     * There a fixed body offset by the scroll it had holds the page exactly
     * where they left it, and it is the offset that is put back.
     *
     * @private
     */
    _lockPage() {
        if (document.body.classList.contains('mk_cookies_locked')) {
            return;
        }
        const scrollerEl = this._getScrollerEl();
        if (scrollerEl) {
            this.lockedScroll = scrollerEl.scrollTop;
            scrollerEl.style.overflow = 'hidden';
        } else {
            this.lockedScroll = window.scrollY;
            document.body.style.position = 'fixed';
            document.body.style.width = '100%';
            document.body.style.top = `-${this.lockedScroll}px`;
        }
        document.body.classList.add('mk_cookies_locked');
    },
    /**
     * Give the page its scrolling, and its scroll position, back.
     *
     * @private
     */
    _unlockPage() {
        if (!document.body.classList.contains('mk_cookies_locked')) {
            return;
        }
        document.body.classList.remove('mk_cookies_locked');
        const scrollerEl = this._getScrollerEl();
        if (scrollerEl) {
            scrollerEl.style.overflow = '';
            scrollerEl.scrollTop = this.lockedScroll ?? 0;
        } else {
            document.body.style.position = '';
            document.body.style.width = '';
            document.body.style.top = '';
            window.scrollTo(0, this.lockedScroll ?? 0);
        }
    },
    /**
     * Show the first layer again, claiming nothing it does not have.
     *
     * @private
     */
    _showNotice() {
        this.preferencesEl?.classList.add('d-none');
        this.noticeEl?.classList.remove('d-none');
        this.modalEl.classList.remove('mk_cookies_expanded');
        this.modalEl.setAttribute('aria-labelledby', 'muk_cookies_title');
        this.modalEl.removeAttribute('aria-modal');
        this._unlockPage();
        this._releaseFocusTrap();
    },
    /**
     * Leave the preference centre, putting focus back where it was opened.
     *
     * @private
     */
    _leavePreferences() {
        this._showNotice();
        this.el.querySelector('#muk_cookies_customize')?.focus();
    },
    /**
     * Keep Tab inside the expanded layer, listening on the document.
     *
     * A trap that only hears keys inside the dialog goes silent the moment
     * focus is somewhere else, which is exactly when it is needed.
     *
     * @private
     */
    _installFocusTrap() {
        this._releaseFocusTrap();
        document.addEventListener('keydown', this.__onTrappedKeydown);
        this.focusTrapped = true;
    },
    /**
     * @private
     */
    _releaseFocusTrap() {
        if (!this.focusTrapped) {
            return;
        }
        document.removeEventListener('keydown', this.__onTrappedKeydown);
        this.focusTrapped = false;
    },
    /**
     * Show the notice again, moving focus into it rather than leaving the
     * visitor on the control they pressed.
     *
     * The listener goes on before the dialog is shown: this modal does not
     * fade, so Bootstrap fires `shown` synchronously inside `show()` and a
     * listener added afterwards never runs. A dialog that is already open
     * fires nothing at all, so that case moves focus directly.
     *
     * @private
     */
    _reopen() {
        this._popupAlreadyShown = false;
        this._showNotice();
        this.dismissEl?.classList.toggle('d-none', !this._canDismiss());
        if (this.modalEl.classList.contains('show')) {
            this._focusFirstControl();
            return;
        }
        this.modalEl.addEventListener(
            'shown.bs.modal',
            () => this._focusFirstControl(),
            { once: true },
        );
        this._showPopup();
    },
    /**
     * @private
     */
    _focusFirstControl() {
        const layerEl = this.preferencesEl?.classList.contains('d-none')
            ? this.noticeEl
            : this.preferencesEl;
        layerEl?.querySelector('button, input:not([disabled])')?.focus();
    },
    /**
     * Return whether closing the banner may leave the visitor's choice alone.
     *
     * A first visit has to be answered, which is why the notice offers no way
     * out but a decision. Once a decision is in force, reopening it is the
     * visitor looking, and looking must not cost them their choice: the only
     * other ways out of the reopened banner both write a new one, and refusing
     * would silently withdraw what they came to check.
     *
     * @private
     * @returns {boolean}
     */
    _canDismiss() {
        return !this._isAsking() && !!this._readState();
    },
    /**
     * Close the reopened banner, leaving the decision in force untouched.
     *
     * @private
     */
    _dismiss() {
        if (!this._canDismiss()) {
            return;
        }
        this._showNotice();
        this.dismissEl?.classList.add('d-none');
        this._popupAlreadyShown = true;
        this._hidePopup();
        if (this.reopenerEl?.isConnected) {
            this.reopenerEl.focus();
        }
    },
    /**
     * Return which layer the decision was taken on.
     *
     * @private
     * @returns {string}
     */
    _getSource() {
        return this.preferencesEl?.classList.contains('d-none')
            ? 'banner'
            : 'preferences';
    },

    //--------------------------------------------------------------------------
    // Handlers
    //--------------------------------------------------------------------------

    /**
     * @private
     * @param {MouseEvent} ev
     */
    _onAcceptAllClick(ev) {
        ev.preventDefault();
        this._applyDecision(this._getAllCategories(), 'accept_all', this._getSource());
    },
    /**
     * @private
     * @param {MouseEvent} ev
     */
    _onRejectAllClick(ev) {
        ev.preventDefault();
        const action = this._readState() ? 'withdraw' : 'reject_all';
        this._applyDecision([ESSENTIAL], action, this._getSource());
    },
    /**
     * @private
     * @param {MouseEvent} ev
     */
    _onSaveClick(ev) {
        ev.preventDefault();
        const selected = this._getSelectedCategories();
        const optionalCount = this._getAllCategories().filter(
            (code) => code !== ESSENTIAL,
        ).length;
        let action = 'custom';
        if (selected.length === optionalCount + 1) {
            action = 'accept_all';
        } else if (selected.length === 1) {
            action = this._readState() ? 'withdraw' : 'reject_all';
        }
        this._applyDecision(selected, action, 'preferences');
    },
    /**
     * @private
     * @param {MouseEvent} ev
     */
    _onCustomiseClick(ev) {
        ev.preventDefault();
        this._showPreferences();
    },
    /**
     * @private
     * @param {MouseEvent} ev
     */
    _onBackClick(ev) {
        ev.preventDefault();
        this._leavePreferences();
    },
    /**
     * @private
     * @param {MouseEvent} ev
     */
    _onDismissClick(ev) {
        ev.preventDefault();
        this._dismiss();
    },
    /**
     * Reopen on the event core's blocked-embed placeholder triggers.
     *
     * @override
     */
    _onShowCookiesBar() {
        this._reopen();
    },
    /**
     * Reopen the banner from any control placed outside it.
     *
     * @private
     * @param {MouseEvent} ev
     */
    _onDocumentClick(ev) {
        const allowEl = ev.target.closest('.mk_cookies_allow_embed');
        if (allowEl) {
            ev.preventDefault();
            ev.stopPropagation();
            this._allowEmbed(allowEl);
            return;
        }
        const reopenEl = ev.target.closest('.mk_cookies_reopen');
        if (reopenEl) {
            ev.preventDefault();
            this.reopenerEl = reopenEl;
            this._reopen();
        }
    },
    /**
     * Wrap Tab and Shift+Tab around the controls of the open layer.
     *
     * Recomputed on every press: the tabbable set grows and shrinks as the
     * visitor opens the cookie tables inside the layer.
     *
     * @private
     * @param {KeyboardEvent} ev
     */
    _onTrappedKeydown(ev) {
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
    },
    /**
     * Let Escape leave the layer it opened, and nothing more.
     *
     * A dismissal must not imply consent, and it must not imply a refusal
     * either. Refuse all is the documented way out of a banner that is still
     * asking, which is why it sits on the first layer with the same weight as
     * accept. Once a decision is in force there is nothing left to answer, so
     * Escape closes the banner and leaves that decision exactly as it was.
     *
     * @private
     * @param {KeyboardEvent} ev
     */
    _onModalKeydown(ev) {
        if (ev.key !== 'Escape') {
            return;
        }
        ev.stopImmediatePropagation();
        ev.preventDefault();
        if (this.modalEl.classList.contains('mk_cookies_expanded')) {
            this._leavePreferences();
            return;
        }
        this._dismiss();
    },
    /**
     * Never persist anything when the dialog closes on its own.
     *
     * The parent writes its cookie on hide. Consent is only ever written by an
     * explicit decision, so this override deliberately does nothing.
     *
     * @override
     */
    _onHideModal() {},
});

publicWidget.registry.cookies_bar = CookiesBanner;

export default CookiesBanner;
