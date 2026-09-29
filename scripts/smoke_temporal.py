import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path

from temporalio.client import Client, WorkflowExecutionStatus, WorkflowFailureError
from temporalio.service import RPCError
from temporalio.worker import Worker

from scripts.temporal_probe import RecoveryProbeWorkflow

ROOT = Path(__file__).resolve().parents[1]


async def docker(*arguments: str) -> str:
    process = await asyncio.create_subprocess_exec(
        "docker", *arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
    if process.returncode != 0:
        raise RuntimeError(f"Docker {arguments[0]} failed: {stderr.decode(errors='replace')}")
    return stdout.decode().strip()


async def connect(address: str) -> Client:
    for attempt in range(30):
        try:
            return await asyncio.wait_for(Client.connect(address), timeout=2)
        except (RuntimeError, RPCError, TimeoutError):
            if attempt == 29:
                raise
            await asyncio.sleep(1)
    raise RuntimeError("Temporal did not become ready")


async def run_worker(address: str, queue: str) -> None:
    client = await connect(address)
    async with Worker(client, task_queue=queue, workflows=[RecoveryProbeWorkflow]):
        await asyncio.Event().wait()


async def start_worker(address: str, queue: str) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "scripts.smoke_temporal",
        "--worker",
        "--address",
        address,
        "--queue",
        queue,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


async def stop_worker(process: asyncio.subprocess.Process) -> None:
    if process.returncode is None:
        process.kill()
    await asyncio.wait_for(process.wait(), timeout=10)


async def check() -> None:
    config = json.loads(await docker("compose", "config", "--no-interpolate", "--format", "json"))
    image = config["services"]["temporal"]["image"]
    name = "careeract-recovery-" + uuid.uuid4().hex[:12]
    worker = None
    with tempfile.TemporaryDirectory(prefix="careeract-temporal-") as directory:
        try:
            await docker(
                "run",
                "-d",
                "--name",
                name,
                "-p",
                "127.0.0.1::7233",
                "--mount",
                f"type=bind,source={directory},target=/data",
                image,
                "server",
                "start-dev",
                "--ip",
                "0.0.0.0",
                "--headless",
                "--db-filename",
                "/data/temporal.db",
            )
            address = await docker("port", name, "7233/tcp")
            client = await connect(address)
            worker = await start_worker(address, name)
            handle = await client.start_workflow(
                RecoveryProbeWorkflow.run,
                id=name,
                task_queue=name,
                execution_timeout=timedelta(seconds=120),
            )
            assert (
                await asyncio.wait_for(handle.query(RecoveryProbeWorkflow.state), 20) == "waiting"
            )
            original_run = (await handle.describe()).run_id
            await stop_worker(worker)
            worker = await start_worker(address, name)
            assert (
                await asyncio.wait_for(handle.query(RecoveryProbeWorkflow.state), 20) == "waiting"
            )
            print("PASS: waiting state replays after Worker kill", flush=True)
            await stop_worker(worker)
            worker = None
            await handle.signal(RecoveryProbeWorkflow.release)
            assert (await handle.describe()).status == WorkflowExecutionStatus.RUNNING
            await docker("kill", name)
            await docker("start", name)
            address = await docker("port", name, "7233/tcp")
            client = await connect(address)
            handle = client.get_workflow_handle_for(RecoveryProbeWorkflow.run, name)
            assert (await handle.describe()).run_id == original_run
            worker = await start_worker(address, name)
            assert await asyncio.wait_for(handle.result(), 25) == "completed"
            print("PASS: buffered signal survives server kill; same Run completes", flush=True)
            for suffix, expected in (
                ("cancel", WorkflowExecutionStatus.CANCELED),
                ("timeout", WorkflowExecutionStatus.TIMED_OUT),
            ):
                terminal = await client.start_workflow(
                    RecoveryProbeWorkflow.run,
                    id=f"{name}-{suffix}",
                    task_queue=name,
                    execution_timeout=timedelta(seconds=4 if suffix == "timeout" else 30),
                )
                assert (
                    await asyncio.wait_for(terminal.query(RecoveryProbeWorkflow.state), 15)
                    == "waiting"
                )
                if suffix == "cancel":
                    await terminal.cancel()
                try:
                    await asyncio.wait_for(terminal.result(), 15)
                except WorkflowFailureError:
                    assert (await terminal.describe()).status == expected
                else:
                    raise AssertionError("Expected terminal failure")
                print(f"PASS: {suffix} has expected Temporal status", flush=True)
        finally:
            if worker is not None:
                await stop_worker(worker)
            await docker("rm", "-f", name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--address", default="")
    parser.add_argument("--queue", default="")
    args = parser.parse_args()
    asyncio.run(run_worker(args.address, args.queue) if args.worker else check())


if __name__ == "__main__":
    main()
