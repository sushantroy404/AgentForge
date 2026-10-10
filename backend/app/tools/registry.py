"""Controlled tool registry. The LLM can only emit a tool_id + JSON args; nothing else executes."""
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ValidationError


class UnauthorizedToolError(PermissionError):
    pass


class ToolArgError(ValueError):
    pass


@dataclass
class ToolDef:
    tool_id: str
    description: str
    args_model: type[BaseModel]
    fn: Callable[..., dict]
    example_prompt: str = ""
    expected_tokens: tuple[str, ...] = ()   # tokens a good reply to example_prompt should contain


_REGISTRY: dict[str, ToolDef] = {}


def register_tool(tool_id: str, description: str, args_model: type[BaseModel],
                  example_prompt: str = "", expected_tokens: tuple[str, ...] = ()):
    def deco(fn: Callable[..., dict]):
        _REGISTRY[tool_id] = ToolDef(tool_id, description, args_model, fn, example_prompt, expected_tokens)
        return fn
    return deco


def is_registered(tool_id: str) -> bool:
    return tool_id in _REGISTRY


def get_tool(tool_id: str) -> ToolDef:
    return _REGISTRY[tool_id]


def tool_ids() -> list[str]:
    return list(_REGISTRY)


def list_available_tools() -> list[dict[str, Any]]:
    return [
        {"tool_id": t.tool_id, "description": t.description,
         "parameters_schema": t.args_model.model_json_schema(), "example_prompt": t.example_prompt}
        for t in _REGISTRY.values()
    ]


def execute(tool_id: str, args: dict | None, allowed: list[str]) -> dict:
    if tool_id not in _REGISTRY:
        raise UnauthorizedToolError(f"tool '{tool_id}' is not registered")
    if tool_id not in allowed:
        raise UnauthorizedToolError(f"tool '{tool_id}' is not enabled for this Specialist")
    tool = _REGISTRY[tool_id]
    try:
        parsed = tool.args_model.model_validate(args or {})
    except ValidationError as e:
        raise ToolArgError(f"invalid arguments for {tool_id}: {e.errors()[0]['msg']}") from e
    return tool.fn(**parsed.model_dump())
