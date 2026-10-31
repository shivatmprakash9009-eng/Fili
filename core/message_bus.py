"""Pub/Sub Message Bus for inter-agent communication."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger("message_bus")


class MessageType(str, Enum):
    """Types of messages flowing through the bus."""
    TASK = "task"
    RESULT = "result"
    EVENT = "event"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


@dataclass
class Message:
    """A message sent through the message bus.

    Attributes:
        topic: The topic/channel this message is published to.
        data: Message payload.
        msg_type: Type of the message.
        sender: ID of the sending agent.
        message_id: Unique message ID.
        timestamp: When the message was created.
    """
    topic: str
    data: dict[str, Any]
    msg_type: MessageType = MessageType.EVENT
    sender: str = "system"
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "topic": self.topic,
            "msg_type": self.msg_type.value,
            "sender": self.sender,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }


# Type alias for subscriber callbacks
SubscriberCallback = Callable[[Message], Coroutine[Any, Any, None]]


class MessageBus:
    """Async Pub/Sub message bus for agent communication.

    Supports topic-based subscriptions, message history, and routing.
    """

    def __init__(self, max_history: int = 1000) -> None:
        self._subscribers: dict[str, list[SubscriberCallback]] = {}
        self._history: list[Message] = []
        self._max_history = max_history
        self._lock = asyncio.Lock()

    async def subscribe(self, topic: str, callback: SubscriberCallback) -> None:
        """Subscribe a callback to a topic.

        Args:
            topic: Topic to subscribe to. Use '*' for all topics.
            callback: Async function called when a message is published.
        """
        async with self._lock:
            if topic not in self._subscribers:
                self._subscribers[topic] = []
            self._subscribers[topic].append(callback)
            logger.debug(f"Subscribed to topic '{topic}'")

    async def unsubscribe(self, topic: str, callback: SubscriberCallback) -> None:
        """Remove a callback from a topic."""
        async with self._lock:
            if topic in self._subscribers:
                self._subscribers[topic] = [
                    cb for cb in self._subscribers[topic] if cb != callback
                ]

    async def publish(
        self,
        topic: str,
        data: dict[str, Any],
        sender: str = "system",
        msg_type: MessageType = MessageType.EVENT,
    ) -> Message:
        """Publish a message to a topic.

        Args:
            topic: Topic to publish to.
            data: Message payload.
            sender: Sender agent ID.
            msg_type: Type of message.

        Returns:
            The published Message.
        """
        message = Message(
            topic=topic,
            data=data,
            msg_type=msg_type,
            sender=sender,
        )

        # Store in history
        self._history.append(message)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        logger.debug(f"Publishing to '{topic}' from '{sender}': {msg_type.value}")

        # Notify topic subscribers
        callbacks = self._subscribers.get(topic, [])
        # Also notify wildcard subscribers
        callbacks += self._subscribers.get("*", [])

        tasks = [asyncio.create_task(cb(message)) for cb in callbacks]
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Subscriber error on topic '{topic}': {result}")

        return message

    def get_history(
        self,
        topic: str | None = None,
        sender: str | None = None,
        limit: int = 50,
    ) -> list[Message]:
        """Get message history with optional filters.

        Args:
            topic: Filter by topic.
            sender: Filter by sender.
            limit: Max messages to return.

        Returns:
            List of matching messages (newest last).
        """
        messages = self._history
        if topic:
            messages = [m for m in messages if m.topic == topic]
        if sender:
            messages = [m for m in messages if m.sender == sender]
        return messages[-limit:]

    def get_stats(self) -> dict[str, Any]:
        """Get message bus statistics."""
        return {
            "total_messages": len(self._history),
            "topics": list(self._subscribers.keys()),
            "subscribers_per_topic": {
                t: len(cbs) for t, cbs in self._subscribers.items()
            },
        }
