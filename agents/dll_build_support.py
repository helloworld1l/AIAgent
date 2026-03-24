from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Dict, List


DLL_MARKERS = (
    "dll",
    "dynamic library",
    "shared library",
    "动态库",
    "共享库",
)

BUILD_ACTION_MARKERS = (
    "build",
    "compile",
    "export",
    "package",
    "generate",
    "编译",
    "构建",
    "导出",
    "打包",
    "生成",
)

FOLLOWUP_REFERENCE_MARKERS = (
    "刚才",
    "上一个",
    "上次",
    "刚生成",
    "这个",
    "那个",
    "它",
    "that one",
    "the last",
    "previous",
    "last one",
    "it",
)


def mentions_dynamic_library(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    return bool(normalized) and any(marker in normalized for marker in DLL_MARKERS)


def requests_dynamic_library_build(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized or not mentions_dynamic_library(normalized):
        return False
    return any(marker in normalized for marker in BUILD_ACTION_MARKERS)


def references_previous_artifact(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in FOLLOWUP_REFERENCE_MARKERS)


def extract_build_preferences(text: str) -> Dict[str, Any]:
    normalized = str(text or "").strip().lower()
    target_lang = "C++" if any(token in normalized for token in ("c++", "cpp", "cxx")) else "C"
    build_type = "Debug" if "debug" in normalized or "调试" in normalized else "Release"

    profile = ""
    if any(token in normalized for token in ("msvc", "visual studio", "vs2022", "vs2019")):
        profile = "windows_msvc_dll"
    elif any(token in normalized for token in ("mingw", "gcc")):
        profile = "windows_gcc_dll"
    elif "linux" in normalized:
        profile = "linux_gcc_shared"

    return {
        "target_lang": target_lang,
        "build_type": build_type,
        "profile": profile,
        "generate_report": False,
    }


def inspect_matlab_entrypoint(matlab_file: str | Path) -> Dict[str, Any]:
    path = Path(matlab_file)
    if not path.exists():
        return {
            "status": "error",
            "message": f"MATLAB file not found: {path}",
            "matlab_file": str(path),
            "is_function": False,
            "entry_function": "",
            "entry_args_schema": [],
        }

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8-sig")
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to read MATLAB file: {exc}",
            "matlab_file": str(path),
            "is_function": False,
            "entry_function": "",
            "entry_args_schema": [],
        }

    signature = _extract_function_signature(text)
    if not signature:
        return {
            "status": "skipped",
            "message": "Generated .m file is a script; DLL build requires a MATLAB function entry point.",
            "matlab_file": str(path),
            "is_function": False,
            "entry_function": "",
            "entry_args_schema": [],
        }

    entry_function = signature["entry_function"]
    input_args = signature["input_args"]
    inferred_schema = _infer_entry_args_schema(text, input_args)

    if not inferred_schema:
        return {
            "status": "skipped",
            "message": "Unable to infer MATLAB Coder entry arguments for the generated function.",
            "matlab_file": str(path),
            "is_function": True,
            "entry_function": entry_function,
            "input_args": input_args,
            "entry_args_schema": [],
        }

    return {
        "status": "success",
        "message": "MATLAB function entry point is ready for DLL build.",
        "matlab_file": str(path),
        "is_function": True,
        "entry_function": entry_function,
        "input_args": input_args,
        "entry_args_schema": inferred_schema,
    }


def _extract_function_signature(text: str) -> Dict[str, Any] | None:
    pattern = re.compile(
        r"^\s*function\s+(?:\[[^\]]*\]\s*=\s*|[A-Za-z_]\w*\s*=\s*)?([A-Za-z_]\w*)\s*\(([^)]*)\)",
        re.IGNORECASE,
    )
    for line in text.splitlines()[:80]:
        match = pattern.match(line)
        if not match:
            continue
        entry_function = match.group(1).strip()
        raw_args = match.group(2).strip()
        input_args = [part.strip() for part in raw_args.split(",") if part.strip()]
        return {
            "entry_function": entry_function,
            "input_args": input_args,
        }
    return None


def _infer_entry_args_schema(text: str, input_args: List[str]) -> List[Dict[str, Any]]:
    normalized_args = [item.strip() for item in input_args if item.strip()]
    lowered_args = [item.lower() for item in normalized_args]

    if lowered_args == ["mode", "time", "ts", "x", "u"]:
        state_dim = _infer_dimension_variable(text, "state_dim")
        input_dim = _infer_dimension_variable(text, "input_dim")
        if state_dim is None or input_dim is None or state_dim < 0 or input_dim < 0:
            return []
        return [
            {"name": normalized_args[0], "type": "double_scalar"},
            {"name": normalized_args[1], "type": "double_scalar"},
            {"name": normalized_args[2], "type": "double_scalar"},
            {"name": normalized_args[3], "type": "double_vector", "shape": [state_dim, 1]},
            {"name": normalized_args[4], "type": "double_vector", "shape": [input_dim, 1]},
        ]

    if len(normalized_args) == 1:
        arg_name = normalized_args[0]
        lowered = arg_name.lower()
        if lowered in {"x", "u", "state", "input", "vec", "vector"}:
            return [{"name": arg_name, "type": "double_vector", "shape": [1, 1]}]
        return [{"name": arg_name, "type": "double_scalar"}]

    if not normalized_args:
        return []

    return [{"name": arg_name, "type": "double_scalar"} for arg_name in normalized_args]


def _infer_dimension_variable(text: str, variable_name: str) -> int | None:
    assignments = _extract_assignments(text)
    expr = assignments.get(variable_name)
    if not expr:
        match = re.search(rf"\b{re.escape(variable_name)}\s*=\s*(.+?);", text)
        expr = match.group(1).strip() if match else ""
    if not expr:
        return None
    return _evaluate_dimension_expression(expr, assignments, stack=[])


def _extract_assignments(text: str) -> Dict[str, str]:
    assignments: Dict[str, str] = {}
    pattern = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*(.+?);\s*(?:%.*)?$")
    for line in text.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        name = match.group(1).strip()
        expr = match.group(2).strip()
        assignments.setdefault(name, expr)
    return assignments


def _evaluate_dimension_expression(expr: str, assignments: Dict[str, str], stack: List[str]) -> int | None:
    candidate = str(expr or "").strip()
    if not candidate:
        return None
    candidate = re.sub(r"\s+", " ", candidate)
    max_match = re.fullmatch(r"max\(\s*0\s*,\s*(.+)\)", candidate, flags=re.IGNORECASE)
    if max_match:
        candidate = max_match.group(1).strip()

    size_pattern = re.compile(r"size\(\s*([A-Za-z_]\w*)\s*,\s*([12])\s*\)", re.IGNORECASE)
    previous = None
    while previous != candidate:
        previous = candidate
        candidate = size_pattern.sub(
            lambda match: _replace_size_call(match, assignments, stack),
            candidate,
        )

    token_pattern = re.compile(r"\b([A-Za-z_]\w*)\b")

    def replace_variable(match: re.Match[str]) -> str:
        name = match.group(1)
        if name.lower() in {"max", "min", "size", "zeros", "ones"}:
            return name
        if name not in assignments or name in stack:
            return name
        resolved = _evaluate_dimension_expression(assignments[name], assignments, stack + [name])
        return str(resolved) if resolved is not None else name

    previous = None
    while previous != candidate:
        previous = candidate
        candidate = token_pattern.sub(replace_variable, candidate)

    if re.search(r"[A-Za-z_]", candidate):
        return None

    try:
        parsed = ast.parse(candidate, mode="eval")
        value = _safe_eval_numeric_ast(parsed.body)
    except Exception:
        return None

    try:
        return max(0, int(value))
    except Exception:
        return None


def _replace_size_call(match: re.Match[str], assignments: Dict[str, str], stack: List[str]) -> str:
    variable_name = match.group(1)
    axis = int(match.group(2))
    resolved = _resolve_shape_dimension(variable_name, axis, assignments, stack)
    return str(resolved) if resolved is not None else match.group(0)


def _resolve_shape_dimension(
    variable_name: str,
    axis: int,
    assignments: Dict[str, str],
    stack: List[str],
) -> int | None:
    expr = assignments.get(variable_name)
    if not expr:
        return None
    shape = _infer_shape_from_expression(expr, assignments, stack + [variable_name])
    if not shape:
        return None
    index = 0 if axis == 1 else 1
    return int(shape[index])


def _infer_shape_from_expression(
    expr: str,
    assignments: Dict[str, str],
    stack: List[str],
) -> List[int] | None:
    candidate = str(expr or "").strip()
    if not candidate:
        return None

    matrix_shape = _matrix_shape_from_literal(candidate)
    if matrix_shape:
        return matrix_shape

    zeros_match = re.fullmatch(r"(?:zeros|ones)\(\s*([^,]+?)\s*,\s*([^,]+?)\s*\)", candidate, flags=re.IGNORECASE)
    if zeros_match:
        rows = _evaluate_dimension_expression(zeros_match.group(1), assignments, stack)
        cols = _evaluate_dimension_expression(zeros_match.group(2), assignments, stack)
        if rows is not None and cols is not None:
            return [rows, cols]

    if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", candidate):
        return [1, 1]

    if re.fullmatch(r"[A-Za-z_]\w*", candidate) and candidate not in stack and candidate in assignments:
        return _infer_shape_from_expression(assignments[candidate], assignments, stack + [candidate])

    return None


def _matrix_shape_from_literal(expr: str) -> List[int] | None:
    candidate = str(expr or "").strip()
    if not (candidate.startswith("[") and candidate.endswith("]")):
        return None
    body = candidate[1:-1].strip()
    if not body:
        return [0, 0]

    rows = [row.strip() for row in body.split(";") if row.strip()]
    if not rows:
        return None

    column_count = 0
    for row in rows:
        normalized_row = row.replace(",", " ")
        columns = [token for token in normalized_row.split() if token]
        if not columns:
            return None
        column_count = max(column_count, len(columns))

    return [len(rows), column_count]


def _safe_eval_numeric_ast(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Num):
        return float(node.n)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _safe_eval_numeric_ast(node.operand)
        return operand if isinstance(node.op, ast.UAdd) else -operand
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv)):
        left = _safe_eval_numeric_ast(node.left)
        right = _safe_eval_numeric_ast(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        return left // right
    raise ValueError("Unsupported numeric expression")
