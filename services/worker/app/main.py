import asyncio
import logging

from temporalio.client import Client
from temporalio.worker import Worker

from services.worker.app.settings import settings
from services.worker.workflows.system import SystemHealthWorkflow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_worker() -> None:
    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
    )
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[SystemHealthWorkflow],
    )
    logger.info(
        "Starting Temporal worker namespace=%s task_queue=%s",
        settings.temporal_namespace,
        settings.temporal_task_queue,
    )
    await worker.run()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
