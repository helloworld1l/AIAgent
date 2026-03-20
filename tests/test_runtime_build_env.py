from __future__ import annotations

import unittest

from config.settings import ensure_runtime_env_defaults


class RuntimeBuildEnvDefaultsTest(unittest.TestCase):
    def test_defaults_dry_run_to_disabled(self) -> None:
        env: dict[str, str] = {}

        ensure_runtime_env_defaults(env=env, dry_run=False)

        self.assertEqual(env["LOCAL_BUILD_MCP_DRY_RUN"], "0")

    def test_preserves_explicit_runtime_override(self) -> None:
        env = {"LOCAL_BUILD_MCP_DRY_RUN": "1"}

        ensure_runtime_env_defaults(env=env, dry_run=False)

        self.assertEqual(env["LOCAL_BUILD_MCP_DRY_RUN"], "1")


if __name__ == "__main__":
    unittest.main()
