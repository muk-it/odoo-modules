====================
MuK Cookie Consent
====================

Replaces the built-in cookies bar with a real consent manager. Visitors consent
per purpose instead of all-or-nothing, every decision is recorded as proof,
third-party scripts and embeds are blocked per service until their category is
granted, and Google Consent Mode v2 is signalled automatically.

Installation
============

To install this module, you need to:

Download the module and add it to your Odoo addons folder. Afterward, log on to
your Odoo server and go to the Apps menu. Trigger the debug mode and update the
list by clicking on the "Update Apps List" link. Now install the module by
clicking on the install button.

Upgrade
============

To upgrade this module, you need to:

Download the module and add it to your Odoo addons folder. Restart the server
and log on to your Odoo server. Select the Apps menu and upgrade the module by
clicking on the upgrade button.

Configuration
=============

Consent management follows Odoo's own switch: turn on **Cookies Bar** under
Website > Configuration > Settings > Privacy, and this module takes over the
banner. The **Cookie Consent** section of the same page then offers:

- **Block Before Consent**: strip scripts and embeds of a service until its
  purpose is granted, replacing embeds with a notice.
- **Google Consent Mode**: *Basic* withholds Google tags until a purpose they
  serve is granted, so a refusal keeps them unloaded. *Advanced* loads them
  immediately and allows cookieless pings, which recovers conversion modelling
  but sends data before any consent. Basic is the default.
- **Global Privacy Control**: treat a ``Sec-GPC`` request header as a refusal of
  everything optional, and optionally publish ``/.well-known/gpc.json``.
- **Consent Proof**: record every decision, optionally with a salted hash of the
  truncated visitor IP. No readable address is stored.
- **Policy Link**: where the banner sends visitors for the full policy. Empty uses
  the page Odoo publishes at ``/cookie-policy``, which lists your declarations on
  its own.
- **Policy Version**: raising it asks every visitor again.

How the banner looks is set where you can see it, in the website editor: select
the Cookies Bar block in the sidebar for its **Layout**, its **Density**, the
**Footer Link** and the **Floating Button** that bring a visitor back to their
choice.

Captured keys, purposes, services, declarations and region rules live under
Website > Configuration > Cookie Consent. The consent log sits under
Website > Reporting > Consent Logs. Website editors may read it; only a system
administrator may change or delete a record, and even then the model refuses
anything but the retention purge.

Usage
=====

A first-time visitor is asked before anything optional runs. The first layer
offers *Refuse all*, *Accept all* and *Manage choices*; the second layer lists
every purpose with the cookies it covers, taken from your own declarations.

Nothing optional runs until the visitor agrees:

- Cookies are gated per purpose. Odoo's own ``optional`` cookies, such as UTM
  attribution, follow the marketing purpose.
- Scripts and embeds belonging to a service whose purpose is refused are removed
  from the page server-side, before the browser sees them. A refused embed shows
  a notice in its place; clicking it allows that one embed without changing any
  other choice.
- A service marked **Ask In Place Only** is never released by a purpose, not even
  by *Accept all*. It stays blocked until the visitor allows it where it stands,
  which is how the seeded video and map services are set up: consent to a purpose
  is not consent to load a named third party into the page.
- Google Consent Mode v2 is emitted with all seven signals, ``wait_for_update``,
  ``ads_data_redaction`` and ``url_passthrough``, for whichever Google tag your
  site already loads. Deploying that tag stays Odoo's job, not this module's.
- Plausible is consent-gated, which the built-in bar does not do.

Every decision reloads the page. Scripts that already ran cannot be unloaded, so
a reload is the only way a withdrawal actually takes effect.

A decision stops being relied on when it expires, when you raise the policy
version, or when the cookie registry itself changes: adding a purpose, a service
or a declared cookie asks visitors again automatically, because consent given
against an older disclosure no longer covers the new one.

The seeded declarations cover what Odoo itself stores on a visitor's device: the
session, language and company cookies, the timezone, the live-update and
presence keys, the basket count, a live chat, a survey in progress, the UTM
attribution cookies and the storage the Enterprise appointment and push
notification features use. Everything Odoo can set is declared, whether or not
the app that sets it is installed, so archive the rows you do not need. Your own
third parties are yours to add as services, and a weekly scan of your own pages
lists what they set and load under Captured, with anything no declaration covers
put up for review. Storage keys are read from the scripts that write them, since
a scan runs on the server and cannot open the browser's storage. Blocking works on
``script`` and ``iframe`` sources, so a ``link`` to a font service cannot be held
back: serve those from your own server if they must not load before consent.

Region rules decide how long a decision is relied on. The shipped presets cover
the EU/EEA, the UK and Switzerland, with per-country retention where an
authority has published one, and each preset names its source.

Each consent record stores what the visitor was shown, not only what they chose:
the policy version, a fingerprint of the cookie registry in force, the banner
version, the language, the resolved country and region rule, the granted and the
refused purposes, and a salted hash of the truncated IP. Records are append-only
and pruned by a weekly scheduled action after three years.

Credits
=======

Contributors
------------

* Mathias Markl <mathias.markl@mukit.at>

Author & Maintainer
-------------------

This module is maintained by the `MuK IT GmbH <https://www.mukit.at/>`_.

MuK IT is an Austrian company specialized in customizing and extending Odoo.
We develop custom solutions for your individual needs to help you focus on
your strength and expertise to grow your business.

If you want to get in touch please contact us via mail
(sale@mukit.at) or visit our website (https://mukit.at).
