from __future__ import annotations

import unittest
from pathlib import Path
from uuid import uuid4

from knowledge_base.matlab_generator import MatlabModelGenerator, load_cpp_enum_values


class BuiltinEnumCodegenTest(unittest.TestCase):
    def test_load_cpp_enum_values_supports_explicit_and_implicit_values(self) -> None:
        enum_file = Path(__file__).resolve().parent / f"tmp_def_{uuid4().hex}.cpp"
        try:
            enum_file.write_text(
                """
                enum MSG_SIMU {
                    SM_START = 10100,
                    SM_INFO,
                    SM_INITIALIZE,
                    SM_CONTINUE,
                    SM_STOP = 10106,
                    SM_OUTPUT = 10124,
                };
                """.strip(),
                encoding="utf-8",
            )

            values = load_cpp_enum_values(enum_file)
        finally:
            enum_file.unlink(missing_ok=True)

        self.assertEqual(values["SM_START"], 10100)
        self.assertEqual(values["SM_INFO"], 10101)
        self.assertEqual(values["SM_INITIALIZE"], 10102)
        self.assertEqual(values["SM_CONTINUE"], 10103)
        self.assertEqual(values["SM_STOP"], 10106)
        self.assertEqual(values["SM_OUTPUT"], 10124)

    def test_render_script_uses_builtin_def_cpp_mode_values(self) -> None:
        generator = MatlabModelGenerator()
        params = generator.get_default_params("rocket_launch_1d")
        script = generator.render_script("rocket_launch_1d", params)
        enum_values = load_cpp_enum_values()

        self.assertIn("mode_codes = local_builtin_msg_simu();", script)
        self.assertIn("INIT = mode_codes.SM_INITIALIZE;", script)
        self.assertIn("CONT = mode_codes.SM_CONTINUE;", script)
        self.assertIn("OUT  = mode_codes.SM_OUTPUT;", script)
        self.assertIn("EXIT = mode_codes.SM_STOP;", script)
        self.assertIn("function mode_codes = local_builtin_msg_simu()", script)
        self.assertIn(f"cached_mode_codes.SM_INITIALIZE = {enum_values['SM_INITIALIZE']};", script)
        self.assertIn(f"cached_mode_codes.SM_CONTINUE = {enum_values['SM_CONTINUE']};", script)
        self.assertIn(f"cached_mode_codes.SM_OUTPUT = {enum_values['SM_OUTPUT']};", script)
        self.assertIn(f"cached_mode_codes.SM_STOP = {enum_values['SM_STOP']};", script)
        self.assertNotIn("OUT  = 10111;", script)
        self.assertNotIn(f"INIT = {enum_values['SM_INITIALIZE']};", script)
        self.assertNotIn(f"CONT = {enum_values['SM_CONTINUE']};", script)
        self.assertNotIn(f"OUT  = {enum_values['SM_OUTPUT']};", script)
        self.assertNotIn(f"EXIT = {enum_values['SM_STOP']};", script)


if __name__ == "__main__":
    unittest.main()
