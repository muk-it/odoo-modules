from __future__ import annotations

import email
import email.policy

from odoo.addons.mail.tests.common import MailCommon

MAIL_TEMPLATE = """Return-Path: {return_path}
To: {to}
Received: by mail.example.com (Postfix, from userid 10002)
    id 5DF9ABFB2A; Fri, 10 Aug 2012 16:16:39 +0200 (CEST)
From: {email_from}
Subject: {subject}
MIME-Version: 1.0
Content-Type: text/plain; charset=utf-8
Date: Fri, 10 Aug 2012 14:16:26 +0000
Message-ID: {msg_id}
{extra}
Please route this message.
"""

MAIL_TEMPLATE_ATTACHMENT = """Return-Path: {return_path}
To: {to}
From: {email_from}
Subject: {subject}
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="=_Part_Route"
Date: Fri, 10 Aug 2012 14:16:26 +0000
Message-ID: {msg_id}
{extra}
--=_Part_Route
Content-Type: text/plain; charset=utf-8

Please route this message.
--=_Part_Route
Content-Type: text/plain; charset=utf-8; name="invoice.txt"
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="invoice.txt"

SW52b2ljZSBjb250ZW50

--=_Part_Route--
"""


class MailRouteCommon(MailCommon):
    """Provide raw email building and gateway routing helpers."""

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _build_email(
        self,
        *,
        to: str,
        subject: str = 'Routing Test',
        email_from: str = 'John Doe <john.doe@example.com>',
        return_path: str = '',
        msg_id: str = '<route-1@example.com>',
        extra: str = '',
        template: str = MAIL_TEMPLATE,
    ) -> str:
        """Return a raw RFC 822 email ready to be fed to the mail gateway."""
        return template.format(
            to=to,
            subject=subject,
            email_from=email_from,
            return_path=return_path or '<john.doe@example.com>',
            msg_id=msg_id,
            extra=extra,
        )

    def _route_email(self, raw: str) -> list[tuple]:
        """Return the routes the gateway computes for a raw email.

        :return: the ``(model, thread_id, custom_values, user_id, alias)``
            tuples the routing decided on
        """
        message = email.message_from_string(raw, policy=email.policy.SMTP)
        message_dict = self.env['mail.thread'].message_parse(message)
        return self.env['mail.thread'].message_route(message, message_dict)
