import asyncio
import logging

import httpx
from temporalio.client import Client
from temporalio.worker import Worker

from services.worker.activities.recruiting import RecruitingActivities
from services.worker.app.settings import settings
from services.worker.workflows.recruiting import (
    RecruitingAutomationWorkflow,
    RecruitingReadWorkflow,
    RecruitingReplyWorkflow,
    RecruitingSendWorkflow,
)
from services.worker.workflows.system import SystemHealthWorkflow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_worker() -> None:
    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
    )
    key_file = settings.worker_api_key_file
    if key_file is None:
        raise RuntimeError("Worker API credential is required")
    key = key_file.read_text(encoding="utf-8").strip()
    if len(key) < 32:
        raise RuntimeError("Worker API credential is invalid")
    api_client = httpx.AsyncClient(
        base_url=str(settings.worker_api_base_url),
        headers={"Authorization": f"Bearer {key}"},
        timeout=175,
        follow_redirects=False,
    )
    recruiting = RecruitingActivities(api_client)
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[
            SystemHealthWorkflow,
            RecruitingReplyWorkflow,
            RecruitingReadWorkflow,
            RecruitingSendWorkflow,
            RecruitingAutomationWorkflow,
        ],
        activities=[
            recruiting.generate,
            recruiting.read,
            recruiting.stop_read,
            recruiting.send_reply,
            recruiting.reconcile_send,
            recruiting.automation_step,
            recruiting.halt_automation,
        ],
    )
    logger.info(
        "Starting Temporal worker namespace=%s task_queue=%s",
        settings.temporal_namespace,
        settings.temporal_task_queue,
    )
    try:
        await worker.run()
    finally:
        await api_client.aclose()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
