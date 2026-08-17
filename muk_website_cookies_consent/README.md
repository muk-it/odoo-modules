# MuK Cookie Consent

Replaces the built-in cookies bar with a real consent manager. Visitors consent
per purpose instead of all-or-nothing, every decision is recorded as proof,
third-party scripts and embeds are blocked per service until their category is
granted, and Google Consent Mode v2 is signalled automatically.

## Configuration

Consent management follows Odoo's own switch: turn on **Cookies Bar** under
Website > Configuration > Settings > Privacy, and this module takes over the
banner. The **Cookie Consent** section of the same page then offers:

-   **Block Before Consent**: strip scripts and embeds of a service until its
    purpose is granted, replacing embeds with a notice.
-   **Google Consent Mode**: _Basic_ withholds Google tags until a purpose they
    serve is granted, so a refusal keeps them unloaded. _Advanced_ loads them
    immediately and allows cookieless pings, which recovers conversion modelling
    but sends data before any consent. Basic is the default.
-   **Global Privacy Control**: treat a `Sec-GPC` request header as a refusal of
    everything optional, and optionally publish `/.well-known/gpc.json`.
-   **Consent Proof**: record every decision, optionally with a salted hash of the
    truncated visitor IP. No readable address is stored.
-   **Policy Link**: where the banner sends visitors for the full policy. Empty
    uses the page Odoo publishes at `/cookie-policy`, which lists your
    declarations on its own.
-   **Policy Version**: raising it asks every visitor again.

How the banner looks is set where you can see it, in the website editor: select
the Cookies Bar block in the sidebar for its **Layout**, its **Density**, the
**Footer Link** and the **Floating Button** that bring a visitor back to their
choice.

Captured keys, purposes, services, declarations and region rules live under
Website > Configuration > Cookie Consent. The consent log sits under
Website > Reporting > Consent Logs. Website editors may read it; only a system
administrator may change or delete a record, and even then the model refuses
anything but the retention purge.

## Usage

A first-time visitor is asked before anything optional runs. The first layer
offers _Refuse all_, _Accept all_ and _Manage choices_; the second layer lists
every purpose with the cookies it covers, taken from your own declarations.

Nothing optional runs until the visitor agrees:

-   Cookies are gated per purpose. Odoo's own `optional` cookies, such as UTM
    attribution, follow the marketing purpose.
-   Scripts and embeds belonging to a service whose purpose is refused are removed
    from the page server-side, before the browser sees them. A refused embed shows
    a notice in its place; clicking it allows that one embed without changing any
    other choice.
-   A service marked **Ask In Place Only** is never released by a purpose, not
    even by _Accept all_. It stays blocked until the visitor allows it where it
    stands, which is how the seeded video and map services are set up: consent to
    a purpose is not consent to load a named third party into the page.
-   Google Consent Mode v2 is emitted with all seven signals, `wait_for_update`,
    `ads_data_redaction` and `url_passthrough`, for whichever Google tag your
    site already loads. Deploying that tag stays Odoo's job, not this module's.
-   Plausible is consent-gated, which the built-in bar does not do.

Every decision reloads the page. Scripts that already ran cannot be unloaded, so
a reload is the only way a withdrawal actually takes effect.

A decision stops being relied on when it expires, when you raise the policy
version, or when the cookie registry itself changes: adding a purpose, a service
or a declared cookie asks visitors again automatically, because consent given
against an older disclosure no longer covers the new one.

### What the registry ships with

The seeded declarations cover what Odoo itself stores on a visitor's device —
the session, language and company cookies, the timezone, the live-update and
presence keys, the basket count, a live chat, a survey in progress, the UTM
attribution cookies and the storage the Enterprise appointment and push
notification features use. Everything Odoo can set is declared, whether or not
the app that sets it is installed, so archive the rows you do not need.

Two things it deliberately does not ship:

-   **Your own third parties.** A payment provider's SDK, an advertising pixel
    or anything you paste into the page tracking code is yours to add as a
    service, since only you know which you use. Browse your site as an editor
    and anything undeclared turns up under Captured, ready to be declared.
-   **Stylesheets and fonts.** Blocking works on `script` and `iframe` sources,
    which is what Odoo's own gating covers. A `link` to Google Fonts is neither,
    so it cannot be held back: serve fonts from your own server if you need them
    gone before consent.

### Regions

Region rules decide how long a decision is relied on. The shipped presets cover
the EU/EEA, the UK and Switzerland, with per-country retention where an
authority has published one — and each preset names its source, because several
widely-quoted figures are practitioner convention rather than published
guidance. Austria is a case in point: no re-ask interval is published, so it
defaults to the conservative six months.

### Accessibility

The dialog is built to WCAG 2.2 AA: a real `role="dialog"` labelled by its own
heading, keyboard-operable switches, 24 px minimum targets, and no control
hidden from assistive technology. Modality is claimed only where it is true —
the notice leaves the page usable and does not take your focus, while the
preference centre covers the page and so announces itself as modal, keeps Tab
inside it, and hands focus back to the control that opened it. Escape leaves the
preference centre and never counts as a decision, in either direction.

## Consent records

Each decision is stored with what the visitor was shown, not only what they
chose: the policy version, a fingerprint of the cookie registry in force, the
banner version, the language, the resolved country and region rule, the granted
and the refused purposes, and a salted hash of the truncated IP. Records are
append-only and pruned by a weekly scheduled action after three years.
