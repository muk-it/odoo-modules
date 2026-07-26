from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from odoo import models
from odoo.tests.common import TransactionCase, new_test_user, tagged

import odoo.addons.muk_ai_skills as skills_addon


def _load_post_migration() -> ModuleType:
    """Import the 19.0.1.1.0 post-migration script by path.

    The migration directory name contains dots, so it is not importable
    through the regular package machinery.
    """
    path = (
        Path(skills_addon.__file__).parent
        / 'migrations'
        / '19.0.1.1.0'
        / 'post-migration.py'
    )
    spec = importlib.util.spec_from_file_location(
        'muk_ai_skills_post_migration_19_0_1_1_0', path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged('post_install', '-at_install', 'muk_ai_skills', 'migration')
class TestOwnerBackfillMigration(TransactionCase):
    """Test the 19.0.1.1.0 migration backfilling the owner from the creator."""

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.Skill = cls.env['muk_ai.skill']
        cls.creator = new_test_user(cls.env, login='skill_migration_creator')
        cls.upgrader = new_test_user(cls.env, login='skill_migration_upgrader')
        cls.migration = _load_post_migration()

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _legacy_skill(self, name: str, create_uid: int | None) -> models.BaseModel:
        """Create a skill owned by the upgrader and forced onto ``create_uid``."""
        skill = self.Skill.create(
            {
                'name': name,
                'description': 'Pre-upgrade skill.',
                'owner_id': self.upgrader.id,
            }
        )
        self.env.flush_all()
        self.env.cr.execute(
            'UPDATE muk_ai_skill SET create_uid = %s WHERE id = %s',
            (create_uid, skill.id),
        )
        return skill

    # ----------------------------------------------------------
    # Tests
    # ----------------------------------------------------------

    def test_owner_is_reset_to_the_original_creator(self):
        skill = self._legacy_skill('migrated_skill', self.creator.id)
        self.migration.migrate(self.env.cr, None)
        skill.invalidate_recordset(['owner_id'])
        self.assertEqual(skill.owner_id, self.creator)

    def test_owner_is_kept_when_the_creator_is_unknown(self):
        skill = self._legacy_skill('orphan_skill', None)
        self.migration.migrate(self.env.cr, None)
        skill.invalidate_recordset(['owner_id'])
        self.assertEqual(skill.owner_id, self.upgrader)
