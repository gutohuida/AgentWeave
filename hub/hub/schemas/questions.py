"""Question schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class QuestionCreate(BaseModel):
    from_agent: str = Field(max_length=64)
    question: str = Field(max_length=10000)
    blocking: bool = False
    # Offered answers. Empty means open-ended. Capped so one question cannot render an
    # unbounded wall of buttons in front of an operator deciding under a run's timeout.
    options: List[str] = Field(default_factory=list, max_length=8)


class QuestionAnswer(BaseModel):
    answer: str = Field(max_length=10000)


class QuestionResponse(BaseModel):
    id: str = Field(max_length=128)
    project_id: str = Field(max_length=128)
    from_agent: str = Field(max_length=64)
    question: str = Field(max_length=10000)
    answer: Optional[str] = Field(default=None, max_length=10000)
    answered: bool
    blocking: bool
    options: List[str] = Field(default_factory=list)
    created_at: datetime
    answered_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
