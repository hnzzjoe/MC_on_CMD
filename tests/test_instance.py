from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mc_cli.core import instance


class InstanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.versions = self.root / "versions"
        self.versions.mkdir()

    def make_version(self, name: str, data: dict) -> Path:
        folder = self.versions / name
        folder.mkdir(parents=True)
        (folder / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
        return folder

    def test_merges_inherits_from_chain(self) -> None:
        self.make_version(
            "1.20.1",
            {
                "id": "1.20.1",
                "mainClass": "net.minecraft.client.main.Main",
                "libraries": [
                    {"name": "com.example:shared:1.0"},
                    {"name": "com.example:only-base:1.0"},
                ],
                "arguments": {
                    "game": ["--username", "${auth_player_name}"],
                    "jvm": ["-Dbase=true"],
                },
            },
        )
        child = self.make_version(
            "fabric-1.20.1",
            {
                "id": "fabric-1.20.1",
                "inheritsFrom": "1.20.1",
                "libraries": [
                    {"name": "com.example:shared:2.0"},
                    {"name": "net.fabricmc:fabric-loader:0.15.11"},
                ],
                "arguments": {"jvm": ["-Dchild=true"]},
            },
        )

        merged, chain = instance.resolve_version_json(child)
        self.assertEqual(chain, ["fabric-1.20.1", "1.20.1"])
        self.assertEqual(merged["id"], "fabric-1.20.1")
        self.assertEqual(merged["mainClass"], "net.minecraft.client.main.Main")

        names = [lib["name"] for lib in merged["libraries"]]
        self.assertIn("com.example:shared:2.0", names)
        self.assertNotIn("com.example:shared:1.0", names)
        self.assertIn("com.example:only-base:1.0", names)
        self.assertIn("net.fabricmc:fabric-loader:0.15.11", names)

        self.assertEqual(merged["arguments"]["jvm"], ["-Dbase=true", "-Dchild=true"])
        self.assertEqual(merged["arguments"]["game"], ["--username", "${auth_player_name}"])

    def test_classifier_libraries_are_not_collapsed(self) -> None:
        self.make_version(
            "1.20.1",
            {
                "id": "1.20.1",
                "libraries": [
                    {"name": "org.lwjgl:lwjgl:3.3.1"},
                    {"name": "org.lwjgl:lwjgl:3.3.1:natives-windows"},
                ],
            },
        )
        merged, _ = instance.resolve_version_json(self.versions / "1.20.1")
        self.assertEqual(len(merged["libraries"]), 2)

    def test_inheritance_cycle_is_detected(self) -> None:
        self.make_version("a", {"id": "a", "inheritsFrom": "b"})
        self.make_version("b", {"id": "b", "inheritsFrom": "a"})
        with self.assertRaises(ValueError):
            instance.resolve_version_json(self.versions / "a")

    def test_missing_parent_raises(self) -> None:
        folder = self.make_version("orphan", {"id": "orphan", "inheritsFrom": "missing"})
        with self.assertRaises(FileNotFoundError):
            instance.resolve_version_json(folder)

    def test_rename_updates_folder_json_and_id(self) -> None:
        folder = self.make_version("old", {"id": "old", "libraries": []})
        target = instance.rename_instance(folder, "new")
        self.assertEqual(target.name, "new")
        self.assertFalse(folder.exists())
        self.assertTrue((target / "new.json").is_file())
        self.assertEqual(json.loads((target / "new.json").read_text("utf-8"))["id"], "new")

    def test_clone_keeps_parent_untouched(self) -> None:
        source = self.make_version("source", {"id": "source", "libraries": []})
        (source / "mods").mkdir()
        (source / "mods" / "a.jar").write_bytes(b"x")
        target = instance.clone_instance(source, "copy", with_data=True)
        self.assertTrue((target / "copy.json").is_file())
        self.assertTrue((target / "mods" / "a.jar").is_file())
        self.assertTrue((source / "source.json").is_file())

    def test_delete_only_touches_versions(self) -> None:
        folder = self.make_version("gone", {"id": "gone"})
        instance.delete_instance(folder)
        self.assertFalse(folder.exists())
        with self.assertRaises(ValueError):
            instance.delete_instance(self.root)

    def test_invalid_names_rejected(self) -> None:
        for name in ["", "..", "a/b", "bad:name"]:
            with self.assertRaises(ValueError):
                instance.validate_instance_name(name, self.versions)


if __name__ == "__main__":
    unittest.main()
