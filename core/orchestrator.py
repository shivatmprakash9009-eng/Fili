"""Orchestrator Agent — coordinates all agents, manages workflows and task delegation."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.base_agent import BaseAgent, AgentState
from core.message_bus import MessageBus, MessageType
from core.task import Task, TaskResult, TaskStatus, TaskPriority

logger = logging.getLogger("orchestrator")


class Orchestrator:
    """Central orchestrator that manages agent registry, task queue,
    workflow execution, and inter-agent coordination.

    Features:
        - Agent registry with capability-based discovery
        - Priority task queue
        - Sequential & parallel workflow execution
        - Pipeline management (multi-step workflows)
        - Error recovery & retry
        - Agent health monitoring via heartbeats
    """

    def __init__(self, message_bus: MessageBus | None = None) -> None:
        self._agents: dict[str, BaseAgent] = {}  # agent_id -> agent
        self._capability_map: dict[str, list[str]] = {}  # task_type -> [agent_ids]
        self._task_queue: asyncio.PriorityQueue[Task] = asyncio.PriorityQueue()
        self._results: dict[str, TaskResult] = {}  # task_id -> result
        self._message_bus = message_bus or MessageBus()
        self._running = False
        self._pipelines: dict[str, list[dict[str, Any]]] = {}  # pipeline_name -> steps

    # ── Agent Registry ───────────────────────────────────────────

    def register_agent(self, agent: BaseAgent) -> None:
        """Register an agent and index its capabilities."""
        self._agents[agent.agent_id] = agent
        agent.set_message_bus(self._message_bus)

        for capability in agent.get_capabilities():
            if capability not in self._capability_map:
                self._capability_map[capability] = []
            if agent.agent_id not in self._capability_map[capability]:
                self._capability_map[capability].append(agent.agent_id)

        logger.info(
            f"Registered agent '{agent.name}' (id={agent.agent_id}) "
            f"with capabilities: {agent.get_capabilities()}"
        )

    def unregister_agent(self, agent_id: str) -> None:
        """Remove an agent from the registry."""
        if agent_id in self._agents:
            agent = self._agents.pop(agent_id)
            # Remove from capability map
            for cap, ids in self._capability_map.items():
                if agent_id in ids:
                    ids.remove(agent_id)
            logger.info(f"Unregistered agent '{agent.name}' (id={agent_id})")

    def discover_agents(self, task_type: str) -> list[BaseAgent]:
        """Find agents capable of handling a task type."""
        agent_ids = self._capability_map.get(task_type, [])
        return [self._agents[aid] for aid in agent_ids if aid in self._agents]

    def get_best_agent(self, task_type: str) -> BaseAgent | None:
        """Get the best available agent for a task type (picks idle agent first)."""
        agents = self.discover_agents(task_type)
        if not agents:
            return None
        # Prefer idle agents
        for agent in agents:
            if agent.state == AgentState.IDLE:
                return agent
        # Fall back to any available
        return agents[0]

    # ── Task Management ──────────────────────────────────────────

    async def submit_task(self, task: Task) -> str:
        """Submit a task to the queue.

        Returns:
            The task ID.
        """
        await self._task_queue.put(task)
        logger.info(f"Task {task.task_id} ({task.task_type}) submitted with priority {task.priority.name}")
        return task.task_id

    async def execute_task(self, task: Task) -> TaskResult:
        """Directly execute a task by finding a capable agent.

        Args:
            task: The task to execute.

        Returns:
            TaskResult from the agent.
        """
        agent = self.get_best_agent(task.task_type)
        if agent is None:
            logger.error(f"No agent found for task type '{task.task_type}'")
            return TaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                error=f"No agent available for task type '{task.task_type}'",
            )

        task.assign(agent.agent_id)
        logger.info(f"Assigned task {task.task_id} to agent '{agent.name}'")

        # Publish task event
        await self._message_bus.publish(
            topic="task.assigned",
            data={"task_id": task.task_id, "agent_id": agent.agent_id},
            sender="orchestrator",
            msg_type=MessageType.TASK,
        )

        result = await agent.run_task(task)
        self._results[task.task_id] = result

        # Publish result event
        await self._message_bus.publish(
            topic="task.completed" if result.is_success else "task.failed",
            data={"task_id": task.task_id, "status": result.status.value},
            sender="orchestrator",
            msg_type=MessageType.RESULT,
        )

        return result

    # ── Workflow Execution ───────────────────────────────────────

    async def run_sequential(self, tasks: list[Task]) -> list[TaskResult]:
        """Execute tasks one after another, passing results forward.

        Args:
            tasks: Ordered list of tasks.

        Returns:
            List of TaskResults in order.
        """
        results: list[TaskResult] = []
        previous_result: dict[str, Any] = {}

        for task in tasks:
            # Inject previous result into task payload
            if previous_result:
                task.payload["_previous_result"] = previous_result

            result = await self.execute_task(task)
            results.append(result)

            if result.is_failure:
                logger.error(
                    f"Sequential workflow stopped at task {task.task_id}: {result.error}"
                )
                # Cancel remaining tasks
                for remaining in tasks[tasks.index(task) + 1:]:
                    remaining.cancel()
                    results.append(TaskResult(
                        task_id=remaining.task_id,
                        status=TaskStatus.CANCELLED,
                        error="Cancelled due to previous task failure",
                    ))
                break

            previous_result = result.data

        return results

    async def run_parallel(self, tasks: list[Task]) -> list[TaskResult]:
        """Execute tasks in parallel.

        Args:
            tasks: List of independent tasks.

        Returns:
            List of TaskResults (order may not match input).
        """
        coros = [self.execute_task(task) for task in tasks]
        results = await asyncio.gather(*coros, return_exceptions=True)

        task_results: list[TaskResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                task_results.append(TaskResult(
                    task_id=tasks[i].task_id,
                    status=TaskStatus.FAILED,
                    error=str(result),
                ))
            else:
                task_results.append(result)

        return task_results

    # ── Pipeline Management ──────────────────────────────────────

    def define_pipeline(self, name: str, steps: list[dict[str, Any]]) -> None:
        """Define a reusable multi-step pipeline.

        Args:
            name: Pipeline name.
            steps: List of step dicts with keys:
                - task_type: str
                - payload: dict (optional)
                - priority: str (optional)
                - mode: 'sequential' | 'parallel' (default: 'sequential')
        """
        self._pipelines[name] = steps
        logger.info(f"Pipeline '{name}' defined with {len(steps)} steps")

    async def run_pipeline(
        self,
        name: str,
        initial_payload: dict[str, Any] | None = None,
    ) -> list[TaskResult]:
        """Execute a defined pipeline.

        Args:
            name: Pipeline name.
            initial_payload: Payload for the first task.

        Returns:
            All TaskResults from the pipeline.
        """
        steps = self._pipelines.get(name)
        if steps is None:
            raise ValueError(f"Pipeline '{name}' not found")

        logger.info(f"Running pipeline '{name}' with {len(steps)} steps")
        all_results: list[TaskResult] = []
        carry_data: dict[str, Any] = initial_payload or {}
        accumulated_context: dict[str, Any] = dict(carry_data)
        stage_results: dict[str, Any] = {}

        for i, step in enumerate(steps):
            task_type = step["task_type"]
            # Merge accumulated context with step payload, giving step payload priority
            payload = {
                **accumulated_context,
                **step.get("payload", {}),
                "_previous_result": carry_data,
                "_pipeline_context": accumulated_context,
                "_stage_results": stage_results,
            }
            priority_str = step.get("priority", "MEDIUM")
            priority = TaskPriority[priority_str.upper()]

            task = Task(task_type=task_type, payload=payload, priority=priority)
            logger.info(f"Pipeline '{name}' step {i+1}/{len(steps)}: {task_type}")

            result = await self.execute_task(task)
            all_results.append(result)

            if result.is_failure:
                logger.error(f"Pipeline '{name}' failed at step {i+1}: {result.error}")
                break

            # Carry forward result data and accumulate into context
            carry_data = result.data
            stage_results[task_type] = result.data
            if isinstance(result.data, dict):
                accumulated_context.update(result.data)

        logger.info(
            f"Pipeline '{name}' finished. "
            f"{sum(1 for r in all_results if r.is_success)}/{len(all_results)} succeeded."
        )
        return all_results

    # ── Initialization & Shutdown ────────────────────────────────

    async def initialize_all(self) -> None:
        """Initialize all registered agents."""
        logger.info(f"Initializing {len(self._agents)} agents...")
        for agent in self._agents.values():
            await agent.initialize()
        self._running = True
        logger.info("All agents initialized.")

    async def shutdown_all(self) -> None:
        """Gracefully shut down all agents."""
        logger.info("Shutting down all agents...")
        self._running = False
        for agent in self._agents.values():
            await agent.shutdown()
        logger.info("All agents shut down.")

    # ── Health & Status ──────────────────────────────────────────

    def get_system_status(self) -> dict[str, Any]:
        """Get status of the entire multi-agent system."""
        return {
            "running": self._running,
            "agents": {
                aid: agent.get_status() for aid, agent in self._agents.items()
            },
            "total_results": len(self._results),
            "pipelines": list(self._pipelines.keys()),
            "message_bus": self._message_bus.get_stats(),
            "capability_map": {
                k: list(v) for k, v in self._capability_map.items()
            },
        }

    def get_result(self, task_id: str) -> TaskResult | None:
        """Get the result of a completed task."""
        return self._results.get(task_id)
