"""Shared request and response schemas."""

from pydantic import BaseModel, ConfigDict, Field


class RequestModel(BaseModel):
    """Base class for every HTTP request body model.

    A request body refuses what it cannot honour. An unknown field is a client
    saying something the Hub does not act on; absorbing it silently is how a run
    that the operator believes is supervised proceeds unsupervised (F116). The
    only honest answers are to honour the field or to name it, and a model that
    does not declare it cannot honour it -- so it names it, with a 422 that says
    which field was refused.
    """

    model_config = ConfigDict(extra="forbid")


class ErrorResponse(BaseModel):
    error: str = Field(max_length=10000)


class SuccessResponse(BaseModel):
    success: bool = True
    message: str = Field(default="OK", max_length=10000)


class StatusResponse(BaseModel):
    project_id: str = Field(max_length=128)
    project_name: str = Field(max_length=256)
    message_counts: dict
    task_counts: dict
    question_counts: dict
    agents_active: list
