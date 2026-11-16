==============
MuK AI Browser
==============

Pairs the MuK AI Browser extension for Chrome with Odoo, so the MuK AI chat
runs in the browser's side panel and the agent reads the page open there,
clicks, types, fills forms and navigates, and combines that with its Odoo
tools in one chat. The agent, the site rules, the approvals and the log stay
in Odoo; the extension carries out the browser steps in a "MuK AI" tab group.

Installation
============

To install this module, you need to:

Download the module and add it to your Odoo addons folder. Afterward, log on to
your Odoo server and go to the Apps menu. Trigger the debug mode and update the
list by clicking on the "Update Apps List" link. Now install the module by
clicking on the install button.

Upgrade
=======

To upgrade this module, you need to:

Download the module and add it to your Odoo addons folder. Restart the server
and log on to your Odoo server. Select the Apps menu and upgrade the module by
clicking on the upgrade button.

Configuration
=============

The module needs MuK AI with a provider set up, and the `MuK AI Browser
extension <https://chromewebstore.google.com/detail/fecogbhcchendbojonbojofkiehdacne>`_
in Chrome 116 or newer, or in Microsoft Edge. The link is also under MuK AI >
Settings > Extensions > Browser > Get the Extension. The extension is open
source under Apache-2.0: https://github.com/muk-it/muk-ai-browser-extension

Open the extension's options, enter the Odoo address and click Connect. Log in
to Odoo in the tab that opens; the extension reads a one-time code from the
page, receives a key that only works for the browser, and the tab closes by
itself. Every paired browser is listed under MuK AI > Reports > Browsers,
where it can be disconnected.

Under MuK AI > Settings > Extensions > Browser, choose what the agent does on
a site without a rule (Unknown Sites: allow, ask or block) and how long a
connect code stays valid (Connect Codes). The words that always ask are the
system parameter ``muk_ai_browser.risky_keywords``, a comma-separated list (by
default delete, pay, submit and the like). Site rules are kept under MuK AI >
Configuration > Site Permissions, per user or for everyone, as an exact address
or a pattern such as ``*.example.com``; a rule for everyone that blocks a site
wins over any user rule.

Usage
=====

Open the side panel on any page and ask. The tab you are on joins the
"MuK AI" tab group, and the agent works in that group: it reads the page,
finds elements, clicks, types, fills forms, picks options, scrolls, takes
screenshots, and opens links and search results in tabs of the group. A
record the chat opens, such as the product the agent just created, shows in a
tab of the group as well, while the chat stays in the side panel. Drag a tab
into the group to hand it to the agent; it closes only the tabs it opened.

Reading and navigating never ask; a blocked site is refused. Clicking, typing
and filling ask on a site set to ask, outside an approved plan, on a form
submit, and when a step reads like one of the words that always ask. The
agent's own Odoo counts as allowed. For a task of several steps the agent
proposes a plan with its steps and sites; once approved, it acts on those
sites without asking step by step. It never types into password, payment card
or one-time code fields, and every upload of an Odoo file into a site asks
first. Every step is kept in the chat in Odoo.

A bar above the chat names the company in Odoo whose website or email is on
the site of the agent's tab, with a button to open it, or offers to create it.
The agent reads other tabs of its group without switching to them, and saves a
file from the web, such as a supplier's PDF invoice, as an attachment of an
Odoo record. Right-click selected text on any page to ask about it or turn it
into a contact; Alt+M opens the side panel.

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
