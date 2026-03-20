"""Typed assembly planning model between IR and final block assembly."""

from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ASSEMBLY_PLAN_VERSION = "0.1"


class AssemblyFragmentDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fragment_id: str = Field(min_length=1)
    description: str = ""
    equation: str = ""
    source: Literal["library", "draft"] = "library"
    render_mode: Literal["native", "comment_only"] = "native"
    origin: str = ""


class AssemblyOutputs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifacts: List[str] = Field(default_factory=list)
    signals: List[str] = Field(default_factory=list)


class BlockGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: str = Field(min_length=1)
    stage: Literal["setup", "declare", "solver", "fragment", "update", "output", "custom"]
    block_ids: List[str] = Field(default_factory=list)
    loop_scoped: bool = False
    required: bool = True
    description: str = ""


class AssemblyPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_version: str = Field(default=ASSEMBLY_PLAN_VERSION, min_length=1)
    model_id: str = ""
    model_name: str = ""
    template_family: str = Field(min_length=1)
    governing_form: str = ""
    solver: str = ""
    state_variables: List[str] = Field(default_factory=list)
    equation_fragments: List[str] = Field(default_factory=list)
    fragment_defs: List[AssemblyFragmentDef] = Field(default_factory=list)
    state_equations: List[str] = Field(default_factory=list)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    entities: List[Dict[str, Any]] = Field(default_factory=list)
    outputs: AssemblyOutputs = Field(default_factory=AssemblyOutputs)
    task_goal: str = ""
    ir_version: str = ""
    codegen_strategy: str = "ir_composable_renderer"
    block_groups: List[BlockGroup] = Field(default_factory=list)
    render_blocks: List[str] = Field(default_factory=list)
    domain: Dict[str, Any] = Field(default_factory=dict)
    assumptions: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sync_render_blocks(self) -> "AssemblyPlan":
        flattened = flatten_block_groups(self.block_groups)
        if flattened:
            self.render_blocks = flattened
        return self


def flatten_block_groups(block_groups: List[BlockGroup] | List[Dict[str, Any]]) -> List[str]:
    blocks: List[str] = []
    for group in block_groups:
        if isinstance(group, BlockGroup):
            block_ids = group.block_ids
        elif isinstance(group, dict):
            block_ids = group.get("block_ids", [])
        else:
            block_ids = []
        for block_id in block_ids:
            normalized = str(block_id or "").strip()
            if normalized:
                blocks.append(normalized)
    return blocks


def validate_assembly_plan(payload: Dict[str, Any]) -> AssemblyPlan:
    return AssemblyPlan.model_validate(payload)


__all__ = [
    "ASSEMBLY_PLAN_VERSION",
    "AssemblyFragmentDef",
    "AssemblyOutputs",
    "AssemblyPlan",
    "BlockGroup",
    "flatten_block_groups",
    "validate_assembly_plan",
]
