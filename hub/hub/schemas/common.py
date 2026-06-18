"""Shared response schemas."""

from pydantic import BaseModel, Field


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
