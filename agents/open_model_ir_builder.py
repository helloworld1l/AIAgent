"""Helpers for constructing normalized Open Model IR payloads."""

from __future__ import annotations

from typing import Any, Dict

from agents.open_model_ir_schema import OpenModelIR


class OpenModelIRBuilder:
    def build_model(self, payload: Dict[str, Any] | OpenModelIR) -> OpenModelIR:
        if isinstance(payload, OpenModelIR):
            return payload
        if not isinstance(payload, dict):
            raise TypeError("open model ir payload must be a dict or OpenModelIR")
        return OpenModelIR.model_validate(payload)

    def build(self, payload: Dict[str, Any] | OpenModelIR) -> Dict[str, Any]:
        model = self.build_model(payload)
        return model.model_dump(mode="python", exclude_none=True)


__all__ = ["OpenModelIRBuilder"]
