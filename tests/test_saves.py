from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from mc_cli.commands.saves import _backup_world_name, _zip_save, safe_extract


class SaveArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_safe_extract_blocks_path_traversal(self) -> None:
        archive = self.root / "evil.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("../evil.txt", "nope")
        target = self.root / "extract"
        with self.assertRaises(ValueError):
            with zipfile.ZipFile(archive) as zf:
                safe_extract(zf, target)
        self.assertFalse((self.root / "evil.txt").exists())

    def test_zip_save_roundtrip(self) -> None:
        world = self.root / "saves" / "My World"
        (world / "region").mkdir(parents=True)
        (world / "level.dat").write_bytes(b"level")
        (world / "region" / "r.0.0.mca").write_bytes(b"region")

        archive = self.root / "backup.zip"
        _zip_save(world, archive)

        target = self.root / "restored"
        with zipfile.ZipFile(archive) as zf:
            safe_extract(zf, target)
        self.assertEqual((target / "My World" / "level.dat").read_bytes(), b"level")
        self.assertTrue((target / "My World" / "region" / "r.0.0.mca").is_file())

    def test_backup_name_strips_timestamp(self) -> None:
        self.assertEqual(_backup_world_name("MyWorld_20260101_120000"), "MyWorld")
        self.assertEqual(_backup_world_name("ALL_SAVES_20260101_120000"), "ALL_SAVES")
        self.assertEqual(_backup_world_name("plain"), "plain")


if __name__ == "__main__":
    unittest.main()
