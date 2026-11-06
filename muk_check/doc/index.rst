=========
MuK Check
=========

This module checks a database against editable rules: security settings, exposed
pages, the Odoo version, new store versions and apps that need a database upgrade.
It reports what it finds and changes nothing on its own. Rules can be changed in
the browser and added by other modules.

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

No configuration required. Under *Settings > General Settings > Security Check* you can
turn off the online checks and the notifications. Notifications are posted in the
Administrators channel in Discuss.

Online checks run once a day. They send the technical names of the installed apps
not made by Odoo to apps.odoo.com, and read the tags of the official Odoo image
from Docker Hub. They send no versions and no database name. Neither source is a
documented API, so a check can stop working if the source changes. Everything else
keeps working.

Usage
=====

*Settings > Security Check* shows the score and the open findings. Each finding says why it
matters and how to fix it. Accept a finding with a reason and an end date if it
does not apply to you, for example on a test server. It stops counting until then.
Odoo's daily cleanup deletes runs and resolved findings older than a year. The system
parameter ``muk_check.history_days`` changes that number, and 0 keeps them forever.
On Odoo.sh, Odoo's platform manages the server, so the server rules and the build
comparison with the Odoo image show Not Applicable.

*Apps > Update Check* lists the installed apps that are not made by Odoo:

* **Store Update**: the store has a newer version than the code on disk. Open the
  store page. An app that is not on the store simply shows no version.
* **Upgrade Needed**: data files, migration scripts, fields or table constraints
  changed since the last upgrade. Changes to Python methods and to JavaScript need
  no upgrade and are not reported. Upgrade the app, or dismiss the flag when the
  change is harmless. Field changes show after a server restart. A changed ``init``
  method in Python cannot be detected.
* **Translations Changed**: database terms in a translation file changed. A normal
  upgrade adds new terms but keeps existing ones. Load the new terms, or overwrite
  to also apply changed wording, which replaces translations customized in this
  database.
* **Missing**: the app is installed but its code is no longer on disk.

What the check cannot see
=========================

The check only sees what Odoo can see from inside, so a good grade does not cover the
server around it. Check these yourself:

* **Backups**: they run, are stored elsewhere, and a restore has been tested.
* **Firewall**: only the ports you need are open, and PostgreSQL is not reachable from
  outside.
* **Login attempts**: a tool such as fail2ban blocks repeated failures at the proxy.
* **SSH**: keys only, without a root login.
* **Operating system**: security updates are installed, also for PostgreSQL.

Rules
=====

*Settings > Security Check > Rules* lists the rules. Turn one off or give it your own
severity, and an upgrade keeps your choice. The logic of a rule a module ships is
read-only so that fixes arrive with new versions. Use *Duplicate* to change it.

A new rule has one of two kinds:

* **Records**: a model and a domain. Each matching record is a finding.
* **Expression**: one Python expression. True, a text, a list of texts or records
  fail the rule. An empty answer passes it, and ``None`` means it does not apply.
  It can use ``env``, ``config()``, ``master_password_is_default()``,
  ``is_odoo_sh()`` and ``datetime``. ``config()`` offers only harmless server options.
  This keeps secrets out of findings by accident, and it is no sandbox: rules are
  written by administrators, who can already run code in server actions.

*Needs Modules* holds technical names as plain text. Without those modules the rule
shows Not Applicable, so a rule about the website needs no dependency on it. Every
rule runs in a savepoint that is always rolled back, so its changes through the ORM
are undone. A rule that fails with an error shows that error, and the others still
run. A rule reports at most 200 records.

Another module adds rules with an XML file. For anything longer than one expression,
call one of its own methods:

.. code-block:: xml

    <record id="rule_negative_stock" model="muk_check.rule">
        <field name="name">Some products have negative stock</field>
        <field name="severity">medium</field>
        <field name="module_ids" eval="[Command.set([ref('base.module_stock')])]"/>
        <field name="kind">expression</field>
        <field name="expression">env['stock.quant']._check_negative_stock()</field>
    </record>

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
