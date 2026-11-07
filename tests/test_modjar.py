from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from mc_cli.core.modjar import looks_like_mod_jar, read_mod_metadata


def make_jar(path: Path, files: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return path


class ModJarTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_reads_fabric_metadata(self) -> None:
        jar = make_jar(
            self.root / "sodium.jar",
            {
                "fabric.mod.json": json.dumps(
                    {"id": "sodium", "name": "Sodium", "version": "0.5.8"}
                )
            },
        )
        self.assertTrue(looks_like_mod_jar(jar))
        meta = read_mod_metadata(jar)
        self.assertIsNotNone(meta)
        self.assertEqual(meta.mod_id, "sodium")
        self.assertEqual(meta.name, "Sodium")
        self.assertEqual(meta.loader, "Fabric")

    def test_reads_forge_toml(self) -> None:
        jar = make_jar(
            self.root / "jei.jar",
            {
                "META-INF/mods.toml": (
                    'modLoader="javafml"\n'
                    "[[mods]]\n"
                    'modId="jei"\n'
                    'displayName="Just Enough Items"\n'
                    'version="15.0.0"\n'
                )
            },
        )
        meta = read_mod_metadata(jar)
        self.assertIsNotNone(meta)
        self.assertEqual(meta.mod_id, "jei")
        self.assertEqual(meta.loader, "Forge")

    def test_rejects_non_mod_jar(self) -> None:
        jar = make_jar(self.root / "plain.jar", {"some/file.txt": "x"})
        self.assertFalse(looks_like_mod_jar(jar))
        self.assertIsNone(read_mod_metadata(jar))

    def test_rejects_broken_zip(self) -> None:
        broken = self.root / "broken.jar"
        broken.write_bytes(b"not a zip")
        self.assertFalse(looks_like_mod_jar(broken))
        self.assertIsNone(read_mod_metadata(broken))


if __name__ == "__main__":
    unittest.main()
