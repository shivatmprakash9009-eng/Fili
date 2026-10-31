"""Task and TaskResult dataclasses for the Multi-Agent System."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import Any


class TaskPriority(IntEnum):
    """Priority levels for tasks. Lower value = higher priority."""
    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3


class TaskStatus(str, Enum):
    """Status of a task throughout its lifecycle."""
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """Represents a unit of work to be processed by an agent.

    Attributes:
        task_type: The type/category of the task (e.g., 'research_leads').
        payload: Arbitrary data for the task.
        priority: Task priority level.
        task_id: Unique identifier (auto-generated).
        status: Current status.
        created_at: Timestamp of creation.
        assigned_to: Agent ID the task is assigned to.
        dependencies: List of task IDs this task depends on.
        metadata: Additional metadata.
    """
    task_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.MEDIUM
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    assigned_to: str | None = None
    dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __lt__(self, other: Task) -> bool:
        """Compare tasks by priority for PriorityQueue."""
        return self.priority < other.priority

    def assign(self, agent_id: str) -> None:
        """Assign task to an agent."""
        self.assigned_to = agent_id
        self.status = TaskStatus.ASSIGNED

    def mark_in_progress(self) -> None:
        self.status = TaskStatus.IN_PROGRESS

    def mark_completed(self) -> None:
        self.status = TaskStatus.COMPLETED

    def mark_failed(self) -> None:
        self.status = TaskStatus.FAILED

    def cancel(self) -> None:
        self.status = TaskStatus.CANCELLED


@dataclass
class TaskResult:
    """Result produced after a task is processed.

    Attributes:
        task_id: The ID of the task that was processed.
        status: Final status.
        data: Result data.
        error: Error message if failed.
        duration_seconds: How long the task took.
        agent_id: Which agent processed it.
    """
    task_id: str
    status: TaskStatus
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_seconds: float = 0.0
    agent_id: str | None = None
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_success(self) -> bool:
        return self.status == TaskStatus.COMPLETED

    @property
    def is_failure(self) -> bool:
        return self.status == TaskStatus.FAILED
