"""Abstract base class for all agents in the Multi-Agent System."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from core.task import Task, TaskResult, TaskStatus


class AgentState(str, Enum):
    """Possible states of an agent."""
    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"
    ERROR = "error"
    COMPLETED = "completed"
    SHUTDOWN = "shutdown"


class BaseAgent(ABC):
    """Abstract base class for all agents.

    Provides: lifecycle management, message passing, state management,
    logging, LLM integration, and retry logic with exponential backoff.
    """

    def __init__(
        self,
        name: str,
        agent_id: str | None = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        self.name = name
        self.agent_id = agent_id or uuid.uuid4().hex[:10]
        self.state = AgentState.IDLE
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._inbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._llm_client: Any | None = None
        self._message_bus: Any | None = None
        self.logger = logging.getLogger(f"agent.{self.name}")
        self.metrics: dict[str, Any] = {
            "tasks_processed": 0,
            "tasks_failed": 0,
            "total_duration": 0.0,
        }

    # ── Lifecycle ────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Initialize the agent. Override for custom setup."""
        self.logger.info(f"[{self.name}] Initializing...")
        self.state = AgentState.IDLE
        self.logger.info(f"[{self.name}] Ready.")

    async def shutdown(self) -> None:
        """Gracefully shut down the agent."""
        self.logger.info(f"[{self.name}] Shutting down...")
        self.state = AgentState.SHUTDOWN
        self.logger.info(f"[{self.name}] Shutdown complete.")

    # ── Task Processing ──────────────────────────────────────────

    async def run_task(self, task: Task) -> TaskResult:
        """Execute a task with retry logic and metrics tracking."""
        self.state = AgentState.RUNNING
        task.mark_in_progress()
        start_time = time.monotonic()
        last_error: str | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                self.logger.info(
                    f"[{self.name}] Processing task {task.task_id} "
                    f"(attempt {attempt}/{self.max_retries})"
                )
                result_data = await self.process_task(task)

                duration = time.monotonic() - start_time
                self.metrics["tasks_processed"] += 1
                self.metrics["total_duration"] += duration
                self.state = AgentState.IDLE
                task.mark_completed()

                return TaskResult(
                    task_id=task.task_id,
                    status=TaskStatus.COMPLETED,
                    data=result_data if isinstance(result_data, dict) else {"result": result_data},
                    duration_seconds=round(duration, 3),
                    agent_id=self.agent_id,
                )
            except Exception as exc:
                last_error = str(exc)
                self.logger.warning(
                    f"[{self.name}] Task {task.task_id} attempt {attempt} failed: {last_error}"
                )
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** (attempt - 1))
                    self.logger.info(f"[{self.name}] Retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)

        # All retries exhausted
        duration = time.monotonic() - start_time
        self.metrics["tasks_failed"] += 1
        self.metrics["total_duration"] += duration
        self.state = AgentState.ERROR
        task.mark_failed()

        return TaskResult(
            task_id=task.task_id,
            status=TaskStatus.FAILED,
            error=last_error,
            duration_seconds=round(duration, 3),
            agent_id=self.agent_id,
        )

    @abstractmethod
    async def process_task(self, task: Task) -> dict[str, Any]:
        """Core task processing logic. Implement in subclasses."""
        ...

    @abstractmethod
    def get_capabilities(self) -> list[str]:
        """Return list of task types this agent can handle."""
        ...

    # ── LLM Integration ──────────────────────────────────────────

    def set_llm_client(self, client: Any) -> None:
        """Attach an LLM client to this agent."""
        self._llm_client = client

    async def call_llm(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        """Call the LLM and return the response text."""
        if self._llm_client is None:
            raise RuntimeError(f"[{self.name}] No LLM client configured.")
        return await self._llm_client.generate_text(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    # ── Messaging ─────────────────────────────────────────────────

    def set_message_bus(self, bus: Any) -> None:
        """Attach a message bus for inter-agent communication."""
        self._message_bus = bus

    async def send_message(self, topic: str, data: dict[str, Any]) -> None:
        """Publish a message to the message bus."""
        if self._message_bus is None:
            self.logger.warning(f"[{self.name}] No message bus configured.")
            return
        await self._message_bus.publish(topic, data, sender=self.agent_id)

    async def receive_message(self, timeout: float = 5.0) -> dict[str, Any] | None:
        """Receive a message from the inbox."""
        try:
            return await asyncio.wait_for(self._inbox.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def deliver_message(self, message: dict[str, Any]) -> None:
        """Deliver a message to this agent's inbox."""
        await self._inbox.put(message)

    # ── Utilities ─────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """Get agent status summary."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "state": self.state.value,
            "metrics": self.metrics.copy(),
        }

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__}(name={self.name!r}, "
            f"id={self.agent_id}, state={self.state.value})>"
        )
