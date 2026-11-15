"""Inputs for the new-project template review, separate from existing data editing."""

from pydantic import BaseModel, ConfigDict, Field


class ControlDraft(BaseModel):
    model_config = ConfigDict(strict=True)

    id: int = 0
    type: str
    label: str
    dataLabel: str
    defaultValue: str
    tooltip: str = ""
    visible: bool = True
    choices: list[str] = Field(default_factory=list)
    includeEmptyChoice: bool = True
    exportToCsv: bool = True
    width: str = "100"
    copyable: bool = True


class TemplateDraft(BaseModel):
    model_config = ConfigDict(strict=True)

    name: str
    revision: str
    controls: list[ControlDraft]
