"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

export function useConfirmAction() {
  const [pending, setPending] = useState<{ action: () => void; description: string; label: string } | null>(null);

  function requestConfirmation(action: () => void, description: string, label = "放弃修改") {
    setPending({ action, description, label });
  }

  const confirmation = <Dialog open={pending !== null} onOpenChange={open => { if (!open) setPending(null); }}>
    <DialogContent>
      <DialogHeader><DialogTitle>确认操作</DialogTitle><DialogDescription>{pending?.description}</DialogDescription></DialogHeader>
      <DialogFooter>
        <Button variant="outline" onClick={() => setPending(null)}>继续编辑</Button>
        <Button onClick={() => { const action = pending?.action; setPending(null); action?.(); }}>{pending?.label}</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>;

  return { requestConfirmation, confirmation };
}
