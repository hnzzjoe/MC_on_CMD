from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mc_cli.core.scanner import scan_instances


def write_version(root: Path, name: str, data: dict) -> Path:
    folder = root / "versions" / name
    folder.mkdir(parents=True)
    (folder / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    return folder


class ScannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "versions").mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_detects_vanilla_fabric_and_forge(self) -> None:
        write_version(self.root, "1.20.1", {"id": "1.20.1", "libraries": []})
        write_version(
            self.root,
            "fabric-1.20.1",
            {
                "id": "fabric-1.20.1",
                "inheritsFrom": "1.20.1",
                "libraries": [{"name": "net.fabricmc:fabric-loader:0.15.11"}],
            },
        )
        write_version(
            self.root,
            "forge-1.20.1",
            {
                "id": "forge-1.20.1",
                "clientVersion": "1.20.1",
                "libraries": [
                    {"name": "net.minecraftforge:forgespi:7.0.1"},
                    {"name": "net.minecraftforge:fmlloader:1.20.1-47.4.20"},
                ],
            },
        )
        result = scan_instances(self.root)
        by_name = {inst.folder_name: inst for inst in result.instances}

        self.assertEqual(by_name["1.20.1"].loader_type, "Vanilla")
        self.assertEqual(by_name["1.20.1"].mc_version, "1.20.1")
        self.assertEqual(by_name["fabric-1.20.1"].loader_type, "Fabric")
        self.assertEqual(by_name["fabric-1.20.1"].loader_version, "0.15.11")
        self.assertEqual(by_name["forge-1.20.1"].loader_type, "Forge")
        self.assertEqual(by_name["forge-1.20.1"].loader_version, "1.20.1-47.4.20")
        self.assertEqual(by_name["forge-1.20.1"].mc_version, "1.20.1")
        self.assertEqual(result.errors, [])

    def test_detects_neoforge_from_fml_libraries(self) -> None:
        write_version(
            self.root,
            "neoforge-1.21.1",
            {
                "id": "neoforge-1.21.1",
                "clientVersion": "1.21.1",
                "mainClass": "cpw.mods.bootstraplauncher.BootstrapLauncher",
                "libraries": [{"name": "net.neoforged.fancymodloader:loader:4.0.42"}],
            },
        )
        result = scan_instances(self.root)
        self.assertEqual(result.instances[0].loader_type, "NeoForge")

    def test_reports_damaged_instances(self) -> None:
        (self.root / "versions" / "broken").mkdir()
        bad = self.root / "versions" / "bad-json"
        bad.mkdir()
        (bad / "bad-json.json").write_text("{not json", encoding="utf-8")

        result = scan_instances(self.root)
        self.assertEqual(result.instances, [])
        messages = " ".join(error.message for error in result.errors)
        self.assertIn("missing version json", messages)
        self.assertIn("invalid json", messages)

    def test_missing_versions_dir_is_an_error(self) -> None:
        result = scan_instances(self.root / "nope")
        self.assertFalse(result.instances)
        self.assertTrue(result.errors)


if __name__ == "__main__":
    unittest.main()
