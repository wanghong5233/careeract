from temporalio import workflow


@workflow.defn
class SystemHealthWorkflow:
    @workflow.run
    async def run(self) -> str:
        return "ok"
