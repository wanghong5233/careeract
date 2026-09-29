from temporalio import workflow


@workflow.defn
class RecoveryProbeWorkflow:
    def __init__(self) -> None:
        self.released = False
        self.phase = "accepted"

    @workflow.run
    async def run(self) -> str:
        self.phase = "waiting"
        await workflow.wait_condition(lambda: self.released)
        self.phase = "completed"
        return self.phase

    @workflow.signal
    def release(self) -> None:
        self.released = True

    @workflow.query
    def state(self) -> str:
        return self.phase
