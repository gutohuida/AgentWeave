"""Question schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class QuestionOption(BaseModel):
    """One offered answer.

    `label` is what comes back when it is chosen; `description` is what lets an operator pick
    without already knowing the trade-off, and is the whole reason options beat a text box.
    """

    label: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=500)

    model_config = {"extra": "forbid"}


class QuestionCreate(BaseModel):
    from_agent: str = Field(max_length=64)
    question: str = Field(max_length=10000)
    blocking: bool = False
    # Offered answers. Empty means open-ended. Capped so one question cannot render an
    # unbounded wall of buttons in front of an operator deciding under a run's timeout.
    options: List[QuestionOption] = Field(default_factory=list, max_length=8)
    header: Optional[str] = Field(default=None, max_length=64)
    multi_select: bool = False


class QuestionAnswer(BaseModel):
    """The operator's answer.

    `answer` is always the human-readable form. `labels` carries the structure when options were
    chosen, so a multi-select answer stays a list rather than a string someone has to re-split.
    """

    answer: str = Field(max_length=10000)
    labels: List[str] = Field(default_factory=list, max_length=8)


class QuestionResponse(BaseModel):
    id: str = Field(max_length=128)
    project_id: str = Field(max_length=128)
    from_agent: str = Field(max_length=64)
    question: str = Field(max_length=10000)
    answer: Optional[str] = Field(default=None, max_length=10000)
    answered: bool
    blocking: bool
    options: List[QuestionOption] = Field(default_factory=list)
    header: Optional[str] = None
    multi_select: bool = False
    answer_labels: List[str] = Field(default_factory=list)
    created_at: datetime
    answered_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
