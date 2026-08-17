"""Model versioning — track progressive learning without online parameter changes.

Each "model version" is an immutable record of:
- a version id (V1, V2, ...)
- the parameters/strategy it represents
- its validation + out-of-sample performance
- the backtest/paper results that justified promoting it

Promotion requires: train -> validate -> backtest -> out-of-sample -> paper -> evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from jarvis.core.logging import get_logger

_log = get_logger("learning.model_versioning")


@dataclass
class ModelVersion:
    version: str  # "V1", "V2", ...
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    performance: dict[str, Any] = field(default_factory=dict)
    promoted: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    evaluation_stage: str = "draft"  # draft|train|validate|backtest|oos|paper|evaluation|promoted

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version, "description": self.description,
            "parameters": self.parameters, "performance": self.performance,
            "promoted": self.promoted, "created_at": self.created_at,
            "evaluation_stage": self.evaluation_stage,
            "id": self.version,
        }


STAGES = ["draft", "train", "validate", "backtest", "oos", "paper", "evaluation", "promoted"]


def next_version_number(memory) -> int:
    versions = memory.model_versions() if memory else []
    nums = []
    for v in versions:
        try:
            n = int(v.get("version", "V0")[1:])
            nums.append(n)
        except (ValueError, IndexError):
            continue
    return (max(nums) + 1) if nums else 1


def register_version(memory, description: str, parameters: dict, performance: dict,
                     stage: str = "draft") -> ModelVersion:
    n = next_version_number(memory)
    mv = ModelVersion(
        version=f"V{n}", description=description, parameters=parameters,
        performance=performance, evaluation_stage=stage,
    )
    if memory is not None:
        memory.record("model_version", mv.as_dict())
        _log.info("registered model version %s stage=%s", mv.version, stage)
    return mv


def promote_version(memory, version: str, performance: dict) -> bool:
    """Mark a version as promoted (active). Demotes all others."""
    if memory is None:
        return False
    versions = memory.model_versions()
    promoted = False
    for v in versions:
        if v.get("version") == version:
            v["promoted"] = True
            v["performance"] = performance
            v["evaluation_stage"] = "promoted"
            memory.record("model_version", v)
            promoted = True
        elif v.get("promoted"):
            v["promoted"] = False
            v["evaluation_stage"] = "evaluation"
            memory.record("model_version", v)
    if promoted:
        _log.info("promoted model version %s", version)
    return promoted


def active_version(memory) -> dict | None:
    versions = memory.model_versions() if memory else []
    for v in versions:
        if v.get("promoted"):
            return v
    return versions[0] if versions else None
