import pathlib
import sys
import tempfile
import unittest
from unittest import mock


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.control_room_launcher import (  # noqa: E402
    SCRIPT_NAMES,
    build_diagnostics,
    build_script_command,
    find_project_root,
    is_project_root,
)


class ControlRoomLauncherTests(unittest.TestCase):
    def test_is_project_root_requires_key_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            self.assertFalse(is_project_root(root))
            for relative_path in ("launch_control_room_hidden.cmd", "README.md", "PRODUCT_COMPLETION_CHECKLIST.md"):
                (root / relative_path).write_text("x", encoding="utf-8")
            self.assertTrue(is_project_root(root))

    def test_build_diagnostics_lists_script_paths(self):
        diagnostics = build_diagnostics(PROJECT_ROOT)
        self.assertTrue(diagnostics["found"])
        self.assertEqual(diagnostics["project_root"], str(PROJECT_ROOT))
        self.assertIn("launch_hidden", diagnostics["scripts"])
        self.assertTrue(diagnostics["scripts"]["launch_hidden"]["path"].endswith(SCRIPT_NAMES["launch_hidden"]))

    def test_build_script_command_uses_cmd_wrapper(self):
        command = build_script_command(PROJECT_ROOT, "launch_control_room_hidden.cmd")
        self.assertEqual(command[1], "/c")
        self.assertTrue(command[2].endswith("launch_control_room_hidden.cmd"))

    def test_find_project_root_uses_candidate_search(self):
        with mock.patch("upbit_auto_trader.control_room_launcher._candidate_roots", return_value=[PROJECT_ROOT]):
            found = find_project_root()
        self.assertEqual(found, PROJECT_ROOT)


if __name__ == "__main__":
    unittest.main()
