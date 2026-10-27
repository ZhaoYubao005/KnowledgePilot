"""Public request/result and constrained model routing contracts."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class CalculatorArguments(StrictModel):
    a: float = Field(strict=True, allow_inf_nan=False)
    b: float = Field(strict=True, allow_inf_nan=False)
    operation: Literal['add', 'subtract', 'multiply', 'divide']


class ToolCall(StrictModel):
    name: Literal['calculator']
    arguments: CalculatorArguments


class Decision(StrictModel):
    route: Literal['direct', 'rag', 'tool']
    tool: ToolCall | None = None

    @model_validator(mode='after')
    def tool_matches_route(self):
        if (self.route == 'tool') != (self.tool is not None):
            raise ValueError('tool is required only for tool route')
        return self


class WorkflowRequest(StrictModel):
    query: str = Field(min_length=1, max_length=8000)
    route: Literal['auto', 'direct', 'rag', 'tool'] = 'auto'
    tool: ToolCall | None = None
    top_k: int = Field(default=3, ge=1, le=20, strict=True)
    document_id: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator('query')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('query must not be blank')
        return value

    @model_validator(mode='after')
    def explicit_tool(self):
        if (self.route == 'tool') != (self.tool is not None):
            raise ValueError('explicit tool is required only for tool route')
        return self


class Evidence(StrictModel):
    content: str
    source: str | None = None


class WorkflowResponse(StrictModel):
    query: str
    route: Literal['auto', 'direct', 'rag', 'tool']
    tool_result: float | None
    evidence: list[Evidence]
    answer: str
    trace: list[str]
    error: Literal['invalid_route', 'tool_failed', 'retrieval_failed'] | None
    status: Literal['completed', 'no_results', 'failed']
