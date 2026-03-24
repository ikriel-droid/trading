import json
import pathlib
import sys
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import upbit_auto_trader.config as config_module  # noqa: E402


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = PROJECT_ROOT / "data" / "test-config-env"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.temp_dir / "test-config.json"
        self.env_path = self.temp_dir / ".env"
        self.original_access = config_module.os.environ.get("UPBIT_ACCESS_KEY")
        self.original_secret = config_module.os.environ.get("UPBIT_SECRET_KEY")
        config_module.os.environ.pop("UPBIT_ACCESS_KEY", None)
        config_module.os.environ.pop("UPBIT_SECRET_KEY", None)
        config_module._LOADED_DOTENV_PATHS.clear()  # noqa: SLF001

    def tearDown(self):
        if self.original_access is not None:
            config_module.os.environ["UPBIT_ACCESS_KEY"] = self.original_access
        else:
            config_module.os.environ.pop("UPBIT_ACCESS_KEY", None)
        if self.original_secret is not None:
            config_module.os.environ["UPBIT_SECRET_KEY"] = self.original_secret
        else:
            config_module.os.environ.pop("UPBIT_SECRET_KEY", None)
        if self.config_path.exists():
            self.config_path.unlink()
        if self.env_path.exists():
            self.env_path.unlink()
        if self.temp_dir.exists():
            self.temp_dir.rmdir()
        config_module._LOADED_DOTENV_PATHS.clear()  # noqa: SLF001

    def test_load_config_reads_dotenv_placeholders(self):
        with open(self.env_path, "w", encoding="utf-8") as handle:
            handle.write("UPBIT_ACCESS_KEY=test-access\n")
            handle.write("UPBIT_SECRET_KEY=\"test-secret\"\n")

        with open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "market": "KRW-BTC",
                    "upbit": {
                        "market": "KRW-BTC",
                        "access_key": "${UPBIT_ACCESS_KEY}",
                        "secret_key": "${UPBIT_SECRET_KEY}",
                    },
                },
                handle,
                indent=2,
            )
            handle.write("\n")

        loaded = config_module.load_config(str(self.config_path))

        self.assertEqual(loaded.upbit.access_key, "test-access")
        self.assertEqual(loaded.upbit.secret_key, "test-secret")

    def test_dotenv_does_not_override_existing_environment(self):
        config_module.os.environ["UPBIT_ACCESS_KEY"] = "already-set"
        with open(self.env_path, "w", encoding="utf-8") as handle:
            handle.write("UPBIT_ACCESS_KEY=from-dotenv\n")

        with open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "market": "KRW-BTC",
                    "upbit": {
                        "market": "KRW-BTC",
                        "access_key": "${UPBIT_ACCESS_KEY}",
                    },
                },
                handle,
                indent=2,
            )
            handle.write("\n")

        loaded = config_module.load_config(str(self.config_path))

        self.assertEqual(loaded.upbit.access_key, "already-set")


if __name__ == "__main__":
    unittest.main()
