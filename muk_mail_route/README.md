# MuK Mail Routing

This module collects incoming emails that matched no alias and no thread, and
lists them as Lost Emails instead of letting them bounce. From there each email
is routed to a new or an existing record, and predefined routers turn one into,
for example, a new CRM lead in a single click. Outgoing emails that could not be
sent are listed as Failed Emails.

## Configuration

Go to **Discuss > Configuration > Routers** to create a router. A router names the
target model and whether an email creates a new record or is attached to an
existing one. For new records, a short Python snippet fills the fields from the
email; the default takes the subject as the name and the sender as the email.

## Usage

Open **Discuss > Lost Emails**. Selecting an email shows it in the preview on the
right. **Route** attaches the selected emails to any record you pick, and each
router adds its own button, such as _Create Lead_. **Discuss > Failed Emails**
lists the outgoing emails that could not be sent.
