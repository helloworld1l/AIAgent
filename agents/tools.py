"""
Tool adapters for MATLAB model knowledge retrieval and .m file generation.
"""

from __future__ import annotations

import json
from typing import Optional

from knowledge_base.matlab_generator import MatlabModelGenerator
from knowledge_base.matlab_model_data import get_model_catalog


class MatlabKnowledgeRetrieverTool:
    name = "matlab_knowledge_retriever"
    description = "Retrieve relevant MATLAB model knowledge entries by natural language description."

    def __init__(self):
        self.generator = MatlabModelGenerator()

    def _run(self, query: str) -> str:
        if not query or not query.strip():
            return json.dumps({"status": "error", "message": "Query is empty."}, ensure_ascii=False)
        matches = self.generator.retrieve_knowledge(query, top_k=5)
        return json.dumps(
            {
                "status": "success",
                "query": query,
                "matches": matches,
            },
            ensure_ascii=False,
            indent=2,
        )


class MatlabFileGeneratorTool:
    name = "matlab_file_generator"
    description = "Generate and save a MATLAB .m script from model description."

    def __init__(self):
        self.generator = MatlabModelGenerator()

    def _run(
        self,
        description: str,
        output_dir: str = "generated_models",
        file_name: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> str:
        result = self.generator.generate_m_file(
            description=description,
            output_dir=output_dir,
            file_name=file_name,
            model_id=model_id,
        )
        return json.dumps(result, ensure_ascii=False, indent=2)


def list_supported_models() -> str:
    catalog = get_model_catalog()
    items = [
        {
            "model_id": m["model_id"],
            "name": m["name"],
            "category": m["category"],
            "description": m["description"],
            "examples": m.get("examples", []),
        }
        for m in catalog
    ]
    return json.dumps({"status": "success", "models": items, "count": len(items)}, ensure_ascii=False, indent=2)

