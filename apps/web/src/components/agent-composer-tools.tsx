"use client";

import { useState, type ReactNode } from "react";
import { Menu } from "@base-ui/react/menu";
import { Popover } from "@base-ui/react/popover";
import { ChevronDown, FileText, ImagePlus, Keyboard, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { TooltipIconButton } from "@/components/tooltip-icon-button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useWorkspaceActions } from "@/components/workspace-actions";
import styles from "./agent-space.module.css";

export function AgentComposerTools({ readOnly, children }: { readOnly: boolean; children: ReactNode }) {
  const { openContent } = useWorkspaceActions();
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [modelOpen, setModelOpen] = useState(false);

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
      <Popover.Trigger render={<Button type="button" variant="ghost" size="sm" disabled={readOnly} aria-label="选择模型" title="查看默认连接与模型切换状态" className={styles.modelSelector} />}>默认模型<ChevronDown className="size-3" /></Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner side="top" align="end" sideOffset={8} className="z-50">
          <Popover.Popup className={styles.modelPopover}>
            <Popover.Title className="text-sm font-medium">模型切换尚未接入</Popover.Title>
            <Popover.Description className="mt-2 text-sm leading-6 text-muted-foreground">文本运行使用服务端默认连接，当前不能在此选择供应商或模型。</Popover.Description>
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
