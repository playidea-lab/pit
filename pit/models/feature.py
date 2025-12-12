"""Feature model"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PullRequest(BaseModel):
    """Pull request info"""

    url: str
    status: str = Field(default="open", pattern="^(open|merged|closed)$")


class GitLink(BaseModel):
    """Git branch/PR linked to a feature"""

    repo: str
    branch: Optional[str] = None
    prs: list[PullRequest] = Field(default_factory=list)


class Checklist(BaseModel):
    """Task/checklist item within a feature"""

    id: str
    label: str
    type: str = Field(default="code", pattern="^(code|test|infra|doc|bug|other)$")
    source: Optional[str] = None
    severity: Optional[str] = None
    urgent: bool = False
    repo: Optional[str] = None
    path_hint: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    due_date: Optional[datetime] = None
    done: bool = False
    done_at: Optional[datetime] = None


class Feature(BaseModel):
    """Feature - main work unit"""

    id: str
    project_id: str
    title: str
    type: str = Field(default="feature", pattern="^(feature|incident|chore)$")
    description: Optional[str] = None
    status: str = Field(
        default="planned",
        pattern="^(planned|in_progress|ready_for_merge|merged|released)$",
    )
    priority: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    owner: Optional[str] = None
    assignees: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    due_date: Optional[datetime] = None
    context: Optional[str] = None
    requirements: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    checklist: list[Checklist] = Field(default_factory=list)
    git_links: list[GitLink] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    @property
    def progress(self) -> tuple[int, int]:
        """Returns (done_count, total_count)"""
        done = sum(1 for t in self.checklist if t.done)
        return done, len(self.checklist)

    @property
    def progress_percent(self) -> int:
        """Returns progress as percentage"""
        done, total = self.progress
        return int(done / total * 100) if total > 0 else 0
