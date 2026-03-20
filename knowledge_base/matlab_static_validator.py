"""Minimal static validation for composed MATLAB scripts."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set

from knowledge_base.blocks import (
    BLOCK_LIBRARY,
    FRAGMENT_FLAG_RULES,
    PARAMETER_DECLARATION_RULES,
    _family_block_id,
)

_MATLAB_RESERVED: Set[str] = {
    "abs",
    "all",
    "and",
    "any",
    "asin",
    "atan",
    "atan2",
    "axis",
    "break",
    "case",
    "catch",
    "clc",
    "clear",
    "close",
    "continue",
    "cos",
    "disp",
    "else",
    "elseif",
    "end",
    "exp",
    "eye",
    "false",
    "figure",
    "for",
    "fprintf",
    "function",
    "grid",
    "hold",
    "hypot",
    "if",
    "inf",
    "legend",
    "length",
    "linspace",
    "log",
    "max",
    "mean",
    "min",
    "mod",
    "nan",
    "nargin",
    "numel",
    "ones",
    "off",
    "on",
    "or",
    "otherwise",
    "pi",
    "plot",
    "return",
    "rng",
    "scatter",
    "semilogy",
    "sin",
    "size",
    "sqrt",
    "subplot",
    "sum",
    "switch",
    "title",
    "true",
    "try",
    "warning",
    "while",
    "xlabel",
    "xlim",
    "ylabel",
    "ylim",
    "zeros",
}

_CONTROL_STARTERS = ("function", "if", "for", "while", "switch", "try")
_CONTROL_CONTINUATIONS = ("else", "elseif", "case", "otherwise", "catch")
_TOKEN_PATTERN = re.compile(r"(?<!\.)\b[A-Za-z_][A-Za-z0-9_]*\b")


class MatlabStaticValidator:
    def validate_assembly(self, assembly: Dict[str, Any]) -> Dict[str, Any]:
        errors: List[str] = []
        warnings: List[str] = []

        if not isinstance(assembly, dict):
            return {
                "valid": False,
                "errors": ["assembly must be a dict"],
                "warnings": [],
            }

        family = str(assembly.get("template_family", "")).strip()
        render_blocks = self._normalize_render_blocks(assembly.get("render_blocks", []))
        parameters = self._normalize_parameters(assembly.get("parameters", {}))

        if not family:
            errors.append("missing assembly.template_family")
        if not render_blocks:
            errors.append("missing assembly.render_blocks")

        unregistered_blocks = [block_id for block_id in render_blocks if block_id not in BLOCK_LIBRARY]
        if unregistered_blocks:
            errors.append("unregistered render blocks: " + ", ".join(unregistered_blocks[:8]))

        if len(render_blocks) != len(set(render_blocks)):
            warnings.append("render_blocks contain duplicates")

        family_blocks = [block_id for block_id in render_blocks if self._is_family_block(block_id)]
        mismatched_blocks = [
            block_id
            for block_id in family_blocks
            if self._block_family(block_id) and self._block_family(block_id) != family
        ]
        if mismatched_blocks:
            errors.append("render_blocks contain blocks from another family: " + ", ".join(mismatched_blocks[:8]))

        declaration_rules = PARAMETER_DECLARATION_RULES.get(family, [])
        missing_params = [
            param_key
            for _, param_key, _ in declaration_rules
            if param_key not in parameters or parameters.get(param_key) is None
        ]
        if missing_params:
            errors.append("missing required parameters: " + ", ".join(dict.fromkeys(missing_params)))

        if family:
            core_blocks = [
                _family_block_id("setup", family, "fragment_flags"),
                _family_block_id("declare", family, "parameters"),
                _family_block_id("solver", family, "loop_begin"),
                _family_block_id("solver", family, "loop_end"),
            ]
            missing_core = [block_id for block_id in core_blocks if block_id not in render_blocks]
            if missing_core:
                errors.append("missing core blocks: " + ", ".join(missing_core))

            has_output = any(block_id.startswith(f"output:{family}:") for block_id in render_blocks)
            if not has_output:
                errors.append(f"missing output block for family {family}")

            loop_begin = _family_block_id("solver", family, "loop_begin")
            loop_end = _family_block_id("solver", family, "loop_end")
            if loop_begin in render_blocks and loop_end in render_blocks:
                begin_index = render_blocks.index(loop_begin)
                end_index = render_blocks.index(loop_end)
                if begin_index >= end_index:
                    errors.append("loop_begin must appear before loop_end")

                declare_block = _family_block_id("declare", family, "parameters")
                if declare_block in render_blocks and render_blocks.index(declare_block) > begin_index:
                    errors.append("parameter declaration block must appear before loop_begin")

                fragment_flag_block = _family_block_id("setup", family, "fragment_flags")
                if fragment_flag_block in render_blocks and render_blocks.index(fragment_flag_block) > begin_index:
                    errors.append("fragment flag block must appear before loop_begin")

                scoped_blocks = [
                    block_id
                    for block_id in render_blocks
                    if block_id.startswith(f"fragment:{family}:") or block_id.startswith(f"update:{family}:")
                ]
                for block_id in scoped_blocks:
                    block_index = render_blocks.index(block_id)
                    if block_index <= begin_index or block_index >= end_index:
                        errors.append(f"loop-scoped block is outside loop: {block_id}")
                        break

                for block_id in render_blocks[end_index + 1 :]:
                    if block_id.startswith(f"fragment:{family}:") or block_id.startswith(f"update:{family}:"):
                        errors.append(f"loop-scoped block appears after loop_end: {block_id}")
                        break

        equation_fragments = [
            str(item).strip()
            for item in assembly.get("equation_fragments", [])
            if str(item).strip()
        ]
        missing_fragment_blocks = [
            fragment_id
            for fragment_id in equation_fragments
            if _family_block_id("fragment", family, fragment_id) not in render_blocks
        ]
        if missing_fragment_blocks:
            warnings.append(
                "equation fragments are present but corresponding fragment blocks are missing: "
                + ", ".join(missing_fragment_blocks[:8])
            )

        if not assembly.get("state_equations"):
            warnings.append("assembly.state_equations is empty")
        if not equation_fragments:
            warnings.append("assembly.equation_fragments is empty")
        if not assembly.get("state_variables"):
            warnings.append("assembly.state_variables is empty")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "family": family,
            "render_blocks": render_blocks,
            "parameters": sorted(parameters.keys()),
        }

    def validate_script(self, script: str, assembly: Dict[str, Any] | None = None) -> Dict[str, Any]:
        errors: List[str] = []
        warnings: List[str] = []
        assembly = assembly if isinstance(assembly, dict) else {}
        script_text = str(script or "")

        if not script_text.strip():
            return {
                "valid": False,
                "errors": ["script is empty"],
                "warnings": [],
                "assigned_variables": [],
                "undefined_variables": [],
            }

        lines = script_text.splitlines()
        executable_lines = [
            self._strip_comments_and_strings(line)
            for line in lines
            if self._strip_comments_and_strings(line).strip()
        ]
        if not executable_lines:
            errors.append("script does not contain executable MATLAB statements")

        if "TODO" in script_text or "{{" in script_text or "}}" in script_text:
            errors.append("script still contains template placeholders")

        if any("\\n" in line for line in executable_lines):
            errors.append("script contains literal \\n tokens")

        control_error = self._check_control_balance(executable_lines)
        if control_error:
            errors.append(control_error)

        bracket_error = self._check_bracket_balance(executable_lines)
        if bracket_error:
            errors.append(bracket_error)

        assigned = self._collect_assigned_variables(script_text)
        family = str(assembly.get("template_family", "")).strip()

        if family:
            render_blocks = self._normalize_render_blocks(assembly.get("render_blocks", []))
            if _family_block_id("declare", family, "parameters") in render_blocks:
                expected_param_vars = [var_name for var_name, _, _ in PARAMETER_DECLARATION_RULES.get(family, [])]
                missing_param_vars = [name for name in expected_param_vars if name not in assigned]
                if missing_param_vars:
                    errors.append("missing parameter declarations in script: " + ", ".join(missing_param_vars))

            if _family_block_id("setup", family, "fragment_flags") in render_blocks:
                expected_flags = [flag_name for flag_name, _ in FRAGMENT_FLAG_RULES.get(family, [])]
                missing_flags = [flag_name for flag_name in expected_flags if flag_name not in assigned]
                if missing_flags:
                    errors.append("missing fragment flag declarations in script: " + ", ".join(missing_flags))

            state_vars = [
                str(item).strip()
                for item in assembly.get("state_variables", [])
                if str(item).strip()
            ]
            missing_state_vars = [name for name in state_vars if name not in assigned]
            if missing_state_vars:
                warnings.append(
                    "state variables not explicitly assigned in script: "
                    + ", ".join(missing_state_vars[:8])
                )

        undefined = self._find_undefined_identifiers(script_text)
        if undefined:
            warnings.append("potentially undefined identifiers: " + ", ".join(undefined[:12]))

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "assigned_variables": sorted(assigned),
            "undefined_variables": undefined,
        }

    def validate_rendered_output(self, assembly: Dict[str, Any], script: str) -> Dict[str, Any]:
        assembly_result = self.validate_assembly(assembly)
        script_result = self.validate_script(script, assembly)
        errors = list(assembly_result.get("errors", [])) + list(script_result.get("errors", []))
        warnings = list(assembly_result.get("warnings", [])) + list(script_result.get("warnings", []))
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "assembly_validation": assembly_result,
            "script_validation": script_result,
        }

    @staticmethod
    def _normalize_render_blocks(value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @staticmethod
    def _normalize_parameters(value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, list):
            normalized: Dict[str, Any] = {}
            for item in value:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                if name:
                    normalized[name] = item.get("value")
            return normalized
        return {}

    @staticmethod
    def _is_family_block(block_id: str) -> bool:
        parts = str(block_id or "").split(":")
        return len(parts) >= 3 and parts[0] in {"setup", "declare", "solver", "fragment", "update", "postprocess", "output"}

    @staticmethod
    def _block_family(block_id: str) -> str:
        parts = str(block_id or "").split(":")
        if len(parts) >= 3:
            return parts[1]
        return ""

    @classmethod
    def _strip_comments_and_strings(cls, line: str) -> str:
        return cls._remove_comments(cls._remove_strings(str(line or "")))

    @staticmethod
    def _remove_comments(line: str) -> str:
        return line.split("%", 1)[0]

    @staticmethod
    def _remove_strings(line: str) -> str:
        result: List[str] = []
        in_string = False
        index = 0
        while index < len(line):
            char = line[index]
            if char == "'":
                if in_string and index + 1 < len(line) and line[index + 1] == "'":
                    index += 2
                    continue
                if not in_string and MatlabStaticValidator._is_transpose_apostrophe(line, index):
                    result.append(char)
                    index += 1
                    continue
                in_string = not in_string
                index += 1
                continue
            if not in_string:
                result.append(char)
            index += 1
        return "".join(result)

    @staticmethod
    def _is_transpose_apostrophe(line: str, index: int) -> bool:
        probe = index - 1
        while probe >= 0 and line[probe].isspace():
            probe -= 1
        if probe < 0:
            return False
        prev_char = line[probe]
        return prev_char.isalnum() or prev_char in ")]}.\"'"

    @staticmethod
    def _split_segments(line: str) -> List[str]:
        return [segment.strip() for segment in str(line or "").split(";") if segment.strip()]

    def _collect_assigned_variables(self, script: str) -> Set[str]:
        assigned: Set[str] = set()
        for raw_line in str(script or "").splitlines():
            code_line = self._strip_comments_and_strings(raw_line)
            if not code_line.strip():
                continue
            assigned.update(self._extract_assigned_variables_from_line(code_line))
        return assigned

    def _find_undefined_identifiers(self, script: str) -> List[str]:
        known: Set[str] = set()
        suspects: List[str] = []
        seen: Set[str] = set()

        for raw_line in str(script or "").splitlines():
            code_line = self._strip_comments_and_strings(raw_line)
            if not code_line.strip():
                continue

            current_assigned = self._extract_assigned_variables_from_line(code_line)
            current_functions = self._extract_function_calls(code_line)
            tokens = _TOKEN_PATTERN.findall(code_line)
            for token in tokens:
                lower = token.lower()
                if lower in _MATLAB_RESERVED:
                    continue
                if token in known or token in current_assigned or token in current_functions:
                    continue
                if token not in seen:
                    seen.add(token)
                    suspects.append(token)
            known.update(current_assigned)

        return suspects

    def _extract_assigned_variables_from_line(self, line: str) -> Set[str]:
        assigned: Set[str] = set()
        for segment in self._split_segments(line):
            loop_match = re.match(r"^for\s+([A-Za-z_][A-Za-z0-9_]*)\s*=", segment)
            if loop_match:
                assigned.add(loop_match.group(1))
                continue

            tuple_match = re.match(r"^\[([^\]]+)\]\s*=", segment)
            if tuple_match:
                for item in tuple_match.group(1).split(","):
                    name = item.strip()
                    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                        assigned.add(name)
                continue

            scalar_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\([^=]*\))?\s*=", segment)
            if scalar_match:
                assigned.add(scalar_match.group(1))

        return assigned

    @staticmethod
    def _extract_function_calls(line: str) -> Set[str]:
        return set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", line))

    @staticmethod
    def _check_control_balance(lines: List[str]) -> str | None:
        depth = 0
        for line in lines:
            for segment in [part.strip() for part in line.split(";") if part.strip()]:
                keyword_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\b", segment)
                if not keyword_match:
                    continue
                keyword = keyword_match.group(1).lower()
                if keyword in _CONTROL_STARTERS:
                    depth += 1
                elif keyword == "end":
                    depth -= 1
                    if depth < 0:
                        return "control block balance failed: unexpected end"
                elif keyword in _CONTROL_CONTINUATIONS and depth <= 0:
                    return f"control block balance failed: unexpected {keyword}"
        if depth != 0:
            return "control block balance failed: missing end"
        return None

    @staticmethod
    def _check_bracket_balance(lines: List[str]) -> str | None:
        round_depth = 0
        square_depth = 0
        for line in lines:
            for char in line:
                if char == "(":
                    round_depth += 1
                elif char == ")":
                    round_depth -= 1
                    if round_depth < 0:
                        return "script health check failed: unmatched ')'"
                elif char == "[":
                    square_depth += 1
                elif char == "]":
                    square_depth -= 1
                    if square_depth < 0:
                        return "script health check failed: unmatched ']'"
        if round_depth != 0:
            return "script health check failed: unmatched ("
        if square_depth != 0:
            return "script health check failed: unmatched '['"
        return None

