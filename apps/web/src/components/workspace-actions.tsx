"use client";

import { createContext, useContext, type ReactNode } from "react";
import { ArrowUpRight } from "lucide-react";
import { Button } from "@/components/ui/button";

export const WorkspaceActionsContext = createContext<{
  openAgent: (prompt?: string) => void;
  openCapabilities: () => void;
  openAccount: () => void;
  openContent: (href: string) => void;
  registerAgent: (handler: (prompt?: string) => void) => () => void;
  registerContent: (handler: (href: string) => void) => () => void;
  describeContent: (content: { href: string; label: string }) => void;
  registerContentDescription: (handler: (content: { href: string; label: string }) => void) => () => void;
} | null>(null);

export function useWorkspaceActions() {
  const actions = useContext(WorkspaceActionsContext);
  if (!actions) throw new Error("Workspace actions require WorkspaceFrame");
  return actions;
}

export function AgentAction({ prompt, children, variant = "default" }: {
  prompt?: string;
  children: ReactNode;
  variant?: "default" | "outline" | "ghost";
}) {
  const { openAgent } = useWorkspaceActions();
  return <Button variant={variant} className="h-9" onClick={() => openAgent(prompt)}>{children}<ArrowUpRight className="size-3.5" /></Button>;
}
