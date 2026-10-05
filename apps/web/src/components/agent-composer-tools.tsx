"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Menu } from "@base-ui/react/menu";
import { Popover } from "@base-ui/react/popover";
import { ChevronDown, FileText, ImagePlus, Keyboard, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { TooltipIconButton } from "@/components/tooltip-icon-button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useWorkspaceActions } from "@/components/workspace-actions";
import { readRuntimeModel } from "@/lib/agent-conversations";
import styles from "./agent-space.module.css";

export function AgentComposerTools({ readOnly, children }: { readOnly: boolean; children: ReactNode }) {
  const { openContent } = useWorkspaceActions();
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [modelOpen, setModelOpen] = useState(false);
  const [model, setModel] = useState<{ id: string; connection: string } | null>(null);
  const [modelError, setModelError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    void readRuntimeModel(AbortSignal.any([controller.signal, AbortSignal.timeout(20_000)])).then(value => { if (!controller.signal.aborted) setModel(value); }).catch((failure: unknown) => { if (!controller.signal.aborted) setModelError(failure instanceof Error ? failure.message : "模型信息读取失败。"); });
    return () => controller.abort();
  }, []);

  return <div className={styles.composerTools}>
    <Menu.Root>
      <Menu.Trigger render={<TooltipIconButton type="button" disabled={readOnly} aria-label="添加内容" tooltip="添加图片或资料" side="top" className="size-8 rounded-full" />}><Plus /></Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner side="top" align="start" sideOffset={8} className="z-50">
          <Menu.Popup className={styles.composerMenu}>
            <Menu.Item disabled className={styles.composerMenuItem}><ImagePlus /><span>上传图片</span><span className={styles.menuStatus}>尚未接入</span></Menu.Item>
            <Menu.Separator className="my-1 border-t" />
            <Menu.Item className={styles.composerMenuItem} onClick={() => openContent("/workspace/library")}><FileText />查看资料与成果</Menu.Item>
            <Menu.Item className={styles.composerMenuItem} onClick={() => setShortcutsOpen(true)}><Keyboard />快捷键</Menu.Item>
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
    <div className={styles.composerTools}>
    <Popover.Root open={modelOpen} onOpenChange={setModelOpen}>
      <Popover.Trigger render={<Button type="button" variant="ghost" size="sm" disabled={readOnly} aria-label="选择模型" title={model ? `当前运行模型：${model.id}` : "查看模型连接状态"} className={styles.modelSelector} />}><span className="max-w-40 truncate">{model?.id ?? (modelError ? "模型读取失败" : "读取模型…")}</span><ChevronDown className="size-3" /></Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner side="top" align="end" sideOffset={8} className="z-50">
          <Popover.Popup className={styles.modelPopover}>
            <Popover.Title className="text-sm font-medium">{model?.id ?? "模型连接"}</Popover.Title>
            <Popover.Description className="mt-2 text-sm leading-6 text-muted-foreground">{model ? `当前使用 ${model.connection} 的运行标识 ${model.id}。模型切换尚未接入。` : modelError || "正在读取服务端实际运行配置。"}</Popover.Description>
            <Button type="button" variant="outline" size="sm" className="mt-4" onClick={() => { setModelOpen(false); openContent("/workspace/settings"); }}>设置与连接</Button>
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
    {children}
    </div>
    <Dialog open={shortcutsOpen} onOpenChange={setShortcutsOpen}>
      <DialogContent>
        <DialogHeader><DialogTitle>快捷键</DialogTitle><DialogDescription>当前支持的常用操作</DialogDescription></DialogHeader>
        <dl className={styles.shortcutList}>
          <div><dt>搜索能力</dt><dd><kbd>Ctrl / ⌘ K</kbd></dd></div>
          <div><dt>发送消息</dt><dd><kbd>Ctrl / ⌘ Enter</kbd></dd></div>
          <div><dt>输入换行</dt><dd><kbd>Enter</kbd></dd></div>
          <div><dt>关闭菜单或弹窗</dt><dd><kbd>Esc</kbd></dd></div>
          <div><dt>搜索结果间移动</dt><dd><kbd>↑ / ↓</kbd></dd></div>
        </dl>
      </DialogContent>
    </Dialog>
  </div>;
}
