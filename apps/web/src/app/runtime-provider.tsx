"use client";

import { HttpAgent } from "@ag-ui/client";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useAgUiRuntime } from "@assistant-ui/react-ag-ui";
import { type ReactNode, useMemo, useState } from "react";

const DEFAULT_AGENT_URL = "http://localhost:8000/agui";

export function RuntimeProvider({ children }: Readonly<{ children: ReactNode }>) {
  const [threadId] = useState(() => crypto.randomUUID());
  const agentUrl =
    process.env.NEXT_PUBLIC_AGUI_AGENT_URL ?? DEFAULT_AGENT_URL;
  const agent = useMemo(
    () =>
      new HttpAgent({
        url: agentUrl,
        threadId,
        headers: { Accept: "text/event-stream" },
      }),
    [agentUrl, threadId],
  );
  const runtime = useAgUiRuntime({ agent });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {children}
    </AssistantRuntimeProvider>
  );
}
