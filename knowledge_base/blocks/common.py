"""Shared helpers for MATLAB IR block registration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Dict, List

if TYPE_CHECKING:
    from knowledge_base.model_family_codegen import MatlabFamilyAssembler

BlockRenderer = Callable[["MatlabFamilyAssembler", Dict[str, Any]], str]
RenderRuleToken = str | Dict[str, Any]
DEFAULT_RENDER_RULE: List[RenderRuleToken] = ["meta:comments", "workspace:clear"]
BLOCK_LIBRARY: Dict[str, BlockRenderer] = {}


def _family_block_id(section: str, family: str, name: str) -> str:
    return f"{section}:{family}:{name}"


def _fragment_group(*names: str, include_remaining: bool = False) -> Dict[str, Any]:
    return {"kind": "fragments", "names": list(names), "include_remaining": include_remaining}


def _standard_family_rule(
    family: str,
    *,
    include_rng: bool = False,
    pre_setup_fragments: List[str] | None = None,
    setup_blocks: List[str] | None = None,
    post_setup_fragments: List[str] | None = None,
    pre_fragment_update_blocks: List[str] | None = None,
    loop_fragments: List[str] | None = None,
    include_remaining_fragments: bool = True,
    post_fragment_update_blocks: List[str] | None = None,
    include_postprocess: bool = True,
    postprocess_block: str = "metrics",
    output_block: str = "plots",
) -> List[RenderRuleToken]:
    rule: List[RenderRuleToken] = ["meta:comments", "workspace:clear"]
    if include_rng:
        rule.append("setup:rng")

    rule.extend(
        [
            _family_block_id("setup", family, "fragment_flags"),
            _family_block_id("declare", family, "parameters"),
        ]
    )

    if pre_setup_fragments:
        rule.append(_fragment_group(*pre_setup_fragments))
    if setup_blocks:
        rule.extend(_family_block_id("setup", family, name) for name in setup_blocks)
    if post_setup_fragments:
        rule.append(_fragment_group(*post_setup_fragments))

    rule.append(_family_block_id("solver", family, "loop_begin"))
    if pre_fragment_update_blocks:
        rule.extend(_family_block_id("update", family, name) for name in pre_fragment_update_blocks)
    if loop_fragments or include_remaining_fragments:
        rule.append(_fragment_group(*(loop_fragments or []), include_remaining=include_remaining_fragments))
    if post_fragment_update_blocks:
        rule.extend(_family_block_id("update", family, name) for name in post_fragment_update_blocks)
    rule.append(_family_block_id("solver", family, "loop_end"))

    if include_postprocess:
        rule.append(_family_block_id("postprocess", family, postprocess_block))
    rule.append(_family_block_id("output", family, output_block))
    return rule


def _join_lines(lines: List[str]) -> str:
    return "\n".join(lines)


def _register_block(registry: Dict[str, BlockRenderer], block_id: str, renderer: BlockRenderer) -> None:
    registry[block_id] = renderer


def _register_text_block(registry: Dict[str, BlockRenderer], block_id: str, text: str) -> None:
    def _renderer(assembler: "MatlabFamilyAssembler", assembly: Dict[str, Any], value: str = text) -> str:
        del assembler, assembly
        return value

    registry[block_id] = _renderer


def _format_numeric_value(value: Any, mode: str | None = None) -> str:
    if mode == "int":
        return str(int(float(value)))
    return str(value)


def _make_fragment_flag_renderer(family: str, flag_rules: List[tuple[str, str]]) -> BlockRenderer:
    def _renderer(assembler: "MatlabFamilyAssembler", assembly: Dict[str, Any]) -> str:
        lines = [
            f"{flag_name} = {assembler._matlab_bool(assembler._has_fragment(assembly, fragment_id))};"
            for flag_name, fragment_id in flag_rules
        ]
        return _join_lines(lines)

    return _renderer


def _make_parameter_renderer(
    declaration_rules: List[tuple[str, str, str | None]],
) -> BlockRenderer:
    def _renderer(assembler: "MatlabFamilyAssembler", assembly: Dict[str, Any]) -> str:
        del assembler
        params = assembly.get("parameters", {})
        lines = [
            f"{var_name} = {_format_numeric_value(params[param_key], cast_mode)};"
            for var_name, param_key, cast_mode in declaration_rules
        ]
        return _join_lines(lines)

    return _renderer


def _render_meta_comments(assembler: "MatlabFamilyAssembler", assembly: Dict[str, Any]) -> str:
    model_name = assembly.get("model_name", assembly.get("template_family", ""))
    return f"%% IR-block-composed MATLAB model: {model_name}\n{assembler._assembly_comments(assembly)}"


_register_block(BLOCK_LIBRARY, "meta:comments", _render_meta_comments)
_register_text_block(BLOCK_LIBRARY, "workspace:clear", "clear; clc; close all;")
_register_text_block(BLOCK_LIBRARY, "setup:rng", "rng(42);")
