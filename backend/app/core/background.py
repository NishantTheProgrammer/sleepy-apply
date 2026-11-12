import asyncio
from typing import Coroutine, Any
import structlog

logger = structlog.get_logger()

# Active detached asyncio tasks managed outside Starlette BackgroundTasks so long-running
# crawlers/pipelines never block Uvicorn HTTP shutdown or reloads.
_active_tasks: set[asyncio.Task[Any]] = set()


def spawn_background_task(name: str, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
    """Schedule a coroutine as a tracked detached asyncio task with exception logging."""
    task = asyncio.create_task(coro, name=name)
    _active_tasks.add(task)

    def _on_done(done_task: asyncio.Task[Any]) -> None:
        _active_tasks.discard(done_task)
        if done_task.cancelled():
            logger.info("Background task cancelled", task_name=name)
            return
        exc = done_task.exception()
        if exc is not None:
            logger.error("Background task failed", task_name=name, error=str(exc))

    task.add_done_callback(_on_done)
    return task


async def cancel_all_background_tasks(timeout: float = 4.0) -> None:
    """Cancel all tracked background tasks cleanly during application shutdown."""
    pending = [t for t in list(_active_tasks) if not t.done()]
    if not pending:
        return

    logger.info("Cancelling tracked background tasks for shutdown", count=len(pending))
    for t in pending:
        t.cancel()

    try:
        await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("Timed out waiting for background tasks to cancel", remaining=len([t for t in pending if not t.done()]))
