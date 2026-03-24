from __future__ import annotations

import os
import unittest

from config.settings import ensure_runtime_env_defaults


class RuntimeBuildEnvDefaultsTest(unittest.TestCase):
    def test_defaults_dry_run_to_disabled(self) -> None:
        env: dict[str, str] = {}

        ensure_runtime_env_defaults(env=env, dry_run=False)

        self.assertEqual(env["LOCAL_BUILD_MCP_DRY_RUN"], "0")
        self.assertTrue(env["MATLAB_PREFDIR"].endswith(".matlab_pref_for_build"))
        self.assertTrue(os.path.isdir(env["MATLAB_PREFDIR"]))

    def test_preserves_explicit_runtime_override(self) -> None:
        env = {"LOCAL_BUILD_MCP_DRY_RUN": "1", "MATLAB_PREFDIR": r"D:\custom_prefdir"}

        ensure_runtime_env_defaults(env=env, dry_run=False)

        self.assertEqual(env["LOCAL_BUILD_MCP_DRY_RUN"], "1")
        self.assertEqual(env["MATLAB_PREFDIR"], r"D:\custom_prefdir")


if __name__ == "__main__":
    unittest.main()
