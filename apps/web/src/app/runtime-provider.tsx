"use client";

import { HttpAgent } from "@ag-ui/client";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useAgUiRuntime } from "@assistant-ui/react-ag-ui";
import { type ReactNode, useMemo, useState } from "react";

const AGENT_BFF_URL = "/api/agent";

export function RuntimeProvider({ children }: Readonly<{ children: ReactNode }>) {
  const [threadId] = useState(() => crypto.randomUUID());
  const agent = useMemo(
    () =>
      new HttpAgent({
        url: AGENT_BFF_URL,
        threadId,
        headers: { Accept: "text/event-stream" },
      }),
    [threadId],
  );
  const runtime = useAgUiRuntime({ agent });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {children}
    </AssistantRuntimeProvider>
  );
}
