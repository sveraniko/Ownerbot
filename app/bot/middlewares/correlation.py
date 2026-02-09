from __future__ import annotations

import uuid
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware

from app.core.logging import set_correlation_id


class CorrelationMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        correlation_id = str(uuid.uuid4())
        set_correlation_id(correlation_id)
        data["correlation_id"] = correlation_id
        return await handler(event, data)
