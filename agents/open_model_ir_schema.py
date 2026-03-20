"""Typed Open Model IR schema used by the open-domain modeling pipeline."""

from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

OPEN_MODEL_IR_VERSION = "0.1"


class TaskIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1)
    request_type: Literal["model_generation", "chat", "clarify", "repair"] = "model_generation"
    language: str = "zh-CN"
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class DomainIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary: str = Field(min_length=1)
    secondary: List[str] = Field(default_factory=list)
    scene: str = ""
    model_family: str = ""
    fidelity: str = ""
    coordinate_system: str = ""
    domain_tags: List[str] = Field(default_factory=list)


class EntityIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    role: str = ""
    states: List[str] = Field(default_factory=list)
    inputs: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)


class PhysicsComponentIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    type: str = ""
    expression: str = ""
    description: str = ""
    target_entity: str = ""
    enabled: bool = True


class ParameterIR(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(min_length=1)
    value: Any = None
    unit: str = ""
    required: bool = False
    label: str = ""
    description: str = ""
    collection_roles: List[str] = Field(default_factory=list)
    source: str = ""


class PhysicsIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    governing_form: str = "ode"
    state_variables: List[str] = Field(default_factory=list)
    state_equations: List[str] = Field(default_factory=list)
    equation_fragments: List[str] = Field(default_factory=list)
    forces: List[PhysicsComponentIR] = Field(default_factory=list)
    parameters: List[ParameterIR] | Dict[str, Any] = Field(default_factory=list)
    initial_conditions: Dict[str, Any] = Field(default_factory=dict)
    assumptions: List[str] = Field(default_factory=list)
    missing_info: List[str] = Field(default_factory=list)


class EventIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    trigger: str = ""
    effect: str = ""
    phase: str = ""
    description: str = ""


class ConstraintIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1)
    target: str = ""
    rule: str = ""
    description: str = ""


class SimulationIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    solver: str = ""
    stop_time: float = Field(ge=0.0)
    time_step_hint: float | None = Field(default=None, gt=0.0)
    sample_count: int | None = Field(default=None, ge=1)


class PlotIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: str = ""
    y: str = ""
    title: str = ""


class OutputsIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signals: List[str] = Field(default_factory=list)
    plots: List[PlotIR] = Field(default_factory=list)
    artifacts: List[str] = Field(default_factory=list)


class CodegenIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str = "matlab_script"
    style: str = ""
    include_comments: bool | None = None
    function_mode: bool | None = None
    strategy: str = ""
    template_family: str = ""
    equation_fragments: List[str] = Field(default_factory=list)


class TraceIR(BaseModel):
    model_config = ConfigDict(extra="allow")

    evidence_domains: List[str] = Field(default_factory=list)
    selected_reason: str = ""
    source: str = ""
    event: str = ""
    query_domains: List[str] = Field(default_factory=list)
    top_family: str = ""
    family_top_share: float | None = Field(default=None, ge=0.0, le=1.0)
    reject_reasons: List[str] = Field(default_factory=list)
    clarify_stage: str = ""
    missing_slots: List[str] = Field(default_factory=list)
    final_generated: bool | None = None
    model_family: str = ""
    domain_tags: List[str] = Field(default_factory=list)
    equation_fragments: List[str] = Field(default_factory=list)


class SlotValueIR(BaseModel):
    model_config = ConfigDict(extra="allow")

    value: Any = None
    source: str = ""


class SlotCollectionIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_family: str = ""
    identify_slots: List[str] = Field(default_factory=list)
    critical_slots: List[str] = Field(default_factory=list)
    defaultable_slots: List[str] = Field(default_factory=list)
    required_slots: List[str] = Field(default_factory=list)
    recommended_slots: List[str] = Field(default_factory=list)
    collected_slots: Dict[str, SlotValueIR] = Field(default_factory=dict)
    filled_parameters: Dict[str, Any] = Field(default_factory=dict)
    missing_slots: List[str] = Field(default_factory=list)
    missing_critical_slots: List[str] = Field(default_factory=list)
    missing_defaultable_slots: List[str] = Field(default_factory=list)
    unresolved_slots: List[str] = Field(default_factory=list)
    collection_stage: str = ""
    status: str = ""
    scene: str = ""
    last_user_reply: str = ""
    used_default_fill: bool = False


class OpenModelIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ir_version: str = Field(default=OPEN_MODEL_IR_VERSION, min_length=1)
    task: TaskIR
    domain: DomainIR
    entities: List[EntityIR]
    physics: PhysicsIR
    events: List[EventIR]
    constraints: List[ConstraintIR]
    simulation: SimulationIR
    outputs: OutputsIR
    codegen: CodegenIR
    trace: TraceIR
    status: str = ""
    task_goal: str = ""
    model_id: str = ""
    model_name: str = ""
    schema_family: str = ""
    clarify_stage: str = ""
    query_domains: List[str] = Field(default_factory=list)
    defaults: Dict[str, Any] = Field(default_factory=dict)
    assumptions: List[str] = Field(default_factory=list)
    required_outputs: List[str] = Field(default_factory=list)
    slot_collection: SlotCollectionIR | None = None
    missing_info: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sync_compatibility_fields(self) -> "OpenModelIR":
        if not self.task_goal:
            self.task_goal = self.task.goal

        if not self.schema_family:
            self.schema_family = (
                self.domain.model_family
                or self.codegen.template_family
                or (self.slot_collection.schema_family if self.slot_collection else "")
            )

        if not self.assumptions and self.physics.assumptions:
            self.assumptions = list(self.physics.assumptions)

        if not self.required_outputs:
            self.required_outputs = list(self.outputs.artifacts or self.outputs.signals)

        if not self.missing_info and self.physics.missing_info:
            self.missing_info = list(self.physics.missing_info)

        if not self.status:
            if self.slot_collection and self.slot_collection.status:
                self.status = self.slot_collection.status
            else:
                self.status = "ready" if not self.missing_info else "needs_clarify"

        if not self.trace.model_family and self.schema_family:
            self.trace.model_family = self.schema_family

        if not self.trace.query_domains and self.query_domains:
            self.trace.query_domains = list(self.query_domains)

        return self


def validate_open_model_ir(payload: Dict[str, Any]) -> OpenModelIR:
    return OpenModelIR.model_validate(payload)


OPEN_MODEL_IR_JSON_SCHEMA: Dict[str, Any] = OpenModelIR.model_json_schema()


__all__ = [
    "OPEN_MODEL_IR_JSON_SCHEMA",
    "OPEN_MODEL_IR_VERSION",
    "CodegenIR",
    "ConstraintIR",
    "DomainIR",
    "EntityIR",
    "EventIR",
    "OpenModelIR",
    "OutputsIR",
    "ParameterIR",
    "PhysicsComponentIR",
    "PhysicsIR",
    "PlotIR",
    "SimulationIR",
    "SlotCollectionIR",
    "SlotValueIR",
    "TaskIR",
    "TraceIR",
    "validate_open_model_ir",
]
