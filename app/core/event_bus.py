import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class WorkspaceEvent:
    type: str
    payload: dict[str, Any]
    workspace_id: str
    event_id: str = field(default_factory=lambda: str(uuid4()))

    def to_sse(self) -> str:
        data = json.dumps({"type": self.type, "payload": self.payload})
        return f"id: {self.event_id}\nevent: {self.type}\ndata: {data}\n\n"


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, workspace_id: str) -> asyncio.Queue:
        q: asyncio.Queue[WorkspaceEvent] = asyncio.Queue(maxsize=100)
        self._subscribers[workspace_id].add(q)
        return q

    def unsubscribe(self, workspace_id: str, q: asyncio.Queue) -> None:
        self._subscribers[workspace_id].discard(q)
        if not self._subscribers[workspace_id]:
            del self._subscribers[workspace_id]

    async def publish(self, event: WorkspaceEvent) -> None:
        dead: list[asyncio.Queue] = []
        for q in set(self._subscribers.get(event.workspace_id, set())):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self.unsubscribe(event.workspace_id, q)


# Import this singleton object everywhere. Never instantiate EventBus directly
event_bus = EventBus()