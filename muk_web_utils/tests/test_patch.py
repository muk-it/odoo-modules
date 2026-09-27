from __future__ import annotations

from odoo.tests import BaseCase

from odoo.addons.muk_web_utils.tools.patch import monkey_patch


class Greeter:
    """Provide a method for ``monkey_patch`` to replace."""

    def greet(self, name: str) -> str:
        """Greet ``name``."""
        return f'hello {name}'


class TestMonkeyPatch(BaseCase):
    """Cover binding a replacement onto a class with ``monkey_patch``."""

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_replacement_delegates_to_the_replaced_attribute(self):
        @monkey_patch(Greeter)
        def greet(self, name: str) -> str:
            """Shout the greeting of the replaced method."""
            return greet.super(self, name).upper()

        @monkey_patch(Greeter)
        def wave(self) -> str:
            """Wave under a name the class does not define."""
            return 'wave'

        self.assertEqual(Greeter().greet('bob'), 'HELLO BOB')
        self.assertEqual(Greeter().wave(), 'wave')
        self.assertIsNone(wave.super)
