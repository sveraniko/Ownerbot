from __future__ import annotations

import asyncio

from app.core.db import check_db
from app.core.redis import check_redis


async def run_checks() -> None:
    await check_db()
    await check_redis()


def main() -> None:
    asyncio.run(run_checks())


if __name__ == "__main__":
    main()
