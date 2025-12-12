"""Project model"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Repo(BaseModel):
    """Git repository linked to a project"""

    name: str
    path: Optional[str] = None
    url: Optional[str] = None


class Project(BaseModel):
    """Project - top level entity"""

    id: str
    name: str
    description: Optional[str] = None
    status: str = Field(default="active", pattern="^(active|paused|archived)$")
    owner: Optional[str] = None
    repos: list[Repo] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    tags: list[str] = Field(default_factory=list)
