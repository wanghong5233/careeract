"use client";

import { RuntimeProvider } from "@/app/runtime-provider";
import { Thread } from "@/components/thread.aui";

export function WorkspaceShell() {
  return (
    <RuntimeProvider>
      <main className="grid h-dvh grid-cols-[15rem_1fr] bg-background">
        <aside className="border-r p-5">
          <h1 className="text-xl font-semibold">CareerAct</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Your personal career agent
          </p>
          <nav className="mt-8 space-y-2 text-sm">
            <div className="rounded-md bg-muted px-3 py-2 font-medium">Agent</div>
            <div className="px-3 py-2 text-muted-foreground">Career profile</div>
            <div className="px-3 py-2 text-muted-foreground">Jobs</div>
            <div className="px-3 py-2 text-muted-foreground">Applications</div>
            <div className="px-3 py-2 text-muted-foreground">Materials</div>
          </nav>
        </aside>
        <section className="min-w-0">
          <Thread />
        </section>
      </main>
    </RuntimeProvider>
  );
}
