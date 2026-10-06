"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Menu } from "@base-ui/react/menu";
import { Check, ChevronDown, FileText, ImagePlus, Keyboard, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { TooltipIconButton } from "@/components/tooltip-icon-button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useWorkspaceActions } from "@/components/workspace-actions";
import { readRuntimeModel, type RuntimeModels } from "@/lib/agent-conversations";
import styles from "./agent-space.module.css";

export function AgentComposerTools({ readOnly, modelDisabled = false, modelId, onModelChange, children }: { readOnly: boolean; modelDisabled?: boolean; modelId?: string | null; onModelChange: (id: string) => void; children: ReactNode }) {
  const { openContent } = useWorkspaceActions();
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [modelOpen, setModelOpen] = useState(false);
  const [model, setModel] = useState<RuntimeModels | null>(null);
  const [modelError, setModelError] = useState("");
  const [modelRevision, setModelRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void readRuntimeModel(AbortSignal.any([controller.signal, AbortSignal.timeout(20_000)])).then(value => { if (!controller.signal.aborted) { setModel(value); setModelError(""); } }).catch((failure: unknown) => { if (!controller.signal.aborted) setModelError(failure instanceof Error ? failure.message : "模型信息读取失败。"); });
    return () => controller.abort();
  }, [modelRevision]);
  const selectedId = modelId ?? model?.id;
  const selected = model?.models.find(item => item.id === selectedId);

  return <div className={styles.composerTools}>
    <Menu.Root>
      <Menu.Trigger render={<TooltipIconButton type="button" disabled={readOnly} aria-label="添加内容" tooltip="添加图片或资料" side="top" className="size-8 rounded-full" />}><Plus /></Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner side="top" align="start" sideOffset={8} className="z-50">
          <Menu.Popup className={styles.composerMenu}>
            <Menu.Item disabled className={styles.composerMenuItem}><ImagePlus /><span>上传图片</span><span className={styles.menuStatus}>尚未接入</span></Menu.Item>
            <Menu.Separator className="my-1 border-t" />
            <Menu.Item className={styles.composerMenuItem} onClick={() => openContent("/library")}><FileText />查看资料与成果</Menu.Item>
            <Menu.Item className={styles.composerMenuItem} onClick={() => setShortcutsOpen(true)}><Keyboard />快捷键</Menu.Item>
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
    <div className={styles.composerTools}>
    <Menu.Root open={modelOpen} onOpenChange={setModelOpen}>
      <Menu.Trigger render={<Button type="button" variant="ghost" size="sm" disabled={readOnly || modelDisabled} aria-label="选择模型" title={modelDisabled ? "运行或保存期间暂不可切换" : selected ? `${selected.provider} · ${selected.model}` : "读取实际模型配置"} className={styles.modelSelector} />}><span className="max-w-40 truncate">{selected?.label ?? (modelError ? "模型读取失败" : model ? "模型配置不可用" : "读取模型…")}</span><ChevronDown className="size-3" /></Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner side="top" align="end" sideOffset={8} className="z-50">
          <Menu.Popup className={styles.composerMenu}>
            <p className="px-3 py-2 text-xs text-muted-foreground">下一次运行使用 · 当前职业上下文保留</p>
            {modelError && <p role="alert" className="px-3 py-2 text-sm">{modelError}</p>}
            {modelError && <Menu.Item className={styles.composerMenuItem} onClick={() => setModelRevision(value => value + 1)}>重新读取模型</Menu.Item>}
            <Menu.RadioGroup value={selectedId ?? ""} onValueChange={id => { if (id !== selectedId) onModelChange(id); setModelOpen(false); }}>
              {Array.from(new Set(model?.models.map(item => item.provider))).map(provider => <Menu.Group key={provider}>
                <Menu.GroupLabel className="px-3 pt-2 text-xs text-muted-foreground">{provider}</Menu.GroupLabel>
                {model?.models.filter(item => item.provider === provider).map(item => <Menu.RadioItem key={item.id} value={item.id} className={styles.composerMenuItem} title={item.model}>
                  <span className="flex-1">{item.label}</span><Menu.RadioItemIndicator><Check className="size-4" /></Menu.RadioItemIndicator>
                </Menu.RadioItem>)}
              </Menu.Group>)}
            </Menu.RadioGroup>
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
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
