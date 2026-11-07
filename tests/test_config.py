from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mc_cli.config import manager


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.patch = mock.patch.dict(os.environ, {"MCCLI_CONFIG_DIR": self.tmp.name})
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_defaults(self) -> None:
        data = manager.load_config()
        self.assertEqual(data["backup_keep"], 10)
        self.assertFalse(data["shared"]["mods"])
        self.assertIsNone(manager.get_mc_dir())

    def test_mc_dir_roundtrip_and_validation(self) -> None:
        folder = Path(self.tmp.name) / "minecraft"
        folder.mkdir()
        manager.save_mc_dir(folder)
        self.assertEqual(manager.get_mc_dir(), folder.resolve())

        # A saved directory that disappears should not be returned.
        folder.rmdir()
        self.assertIsNone(manager.get_mc_dir())

    def test_workspace_roundtrip_and_clear(self) -> None:
        folder = Path(self.tmp.name) / "instance"
        folder.mkdir()
        manager.save_workspace(folder)
        self.assertEqual(manager.get_workspace(), folder.resolve())
        manager.clear_workspace()
        self.assertIsNone(manager.get_workspace())

    def test_multiple_roots(self) -> None:
        first = Path(self.tmp.name) / "a"
        second = Path(self.tmp.name) / "b"
        first.mkdir()
        second.mkdir()

        self.assertTrue(manager.add_mc_dir(first))
        self.assertFalse(manager.add_mc_dir(first))
        self.assertTrue(manager.add_mc_dir(second))
        manager.save_mc_dir(first)

        roots = manager.list_mc_dirs()
        self.assertEqual(roots[0], first.resolve())
        self.assertIn(second.resolve(), roots)

        self.assertTrue(manager.remove_mc_dir(second))
        self.assertNotIn(second.resolve(), manager.list_mc_dirs())

    def test_set_value_and_reset(self) -> None:
        manager.set_value("backup_keep", 20)
        self.assertEqual(manager.get_int("backup_keep", 10), 20)
        self.assertTrue(manager.config_file().is_file())
        manager.reset_config()
        self.assertFalse(manager.config_file().is_file())
        self.assertEqual(manager.get_int("backup_keep", 10), 10)

    def test_config_survives_broken_json(self) -> None:
        manager.config_file().parent.mkdir(parents=True, exist_ok=True)
        manager.config_file().write_text("{broken", encoding="utf-8")
        self.assertEqual(manager.load_config()["backup_keep"], 10)


if __name__ == "__main__":
    unittest.main()
