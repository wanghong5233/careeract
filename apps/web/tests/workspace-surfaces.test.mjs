import assert from "node:assert/strict";
import test from "node:test";
import * as React from "react";
import { loadSource } from "./load-source.mjs";

function text(value) {
  if (Array.isArray(value)) return value.map(text).join(" ");
  if (React.isValidElement(value)) return typeof value.type === "function" ? text(value.type(value.props)) : text(value.props.children);
  return typeof value === "string" ? value : "";
}

const Placeholder = ({ children }) => React.createElement("placeholder", null, children);
const dependencies = {
  react: { ...React, useCallback: callback => callback, useId: () => "synthetic-id", useRef: current => ({ current }), useState: current => [current, () => {}] },
  "next/link": { default: Placeholder },
  "lucide-react": { ArrowRight: Placeholder, ChevronRight: Placeholder, Layers: Placeholder, LockKeyhole: Placeholder, PanelTop: Placeholder, Search: Placeholder },
  "@/components/workspace-actions": { AgentAction: Placeholder },
  "@/components/ui/button": { Button: Placeholder },
  "@/components/ui/dialog": { Dialog: Placeholder, DialogContent: Placeholder, DialogDescription: Placeholder, DialogFooter: Placeholder, DialogHeader: Placeholder, DialogTitle: Placeholder },
  "@/components/workspace-sections": { navigationHref: key => `/${key}`, workspaceSections: [{ key: "inbox", label: "招聘沟通" }, { key: "tasks", label: "Agent 工作" }, { key: "automations", label: "持续委托" }, { key: "reports", label: "工作结果" }, { key: "assistant", label: "Agent 上下文" }] },
  "@/components/workspace-projects": { WorkspaceProjects: Placeholder },
  "@/components/workspace-memories": { WorkspaceMemories: Placeholder },
  "@/components/workspace-materials": { WorkspaceMaterials: Placeholder },
  "@/lib/utils": { cn: (...values) => values.filter(Boolean).join(" ") },
};

test("recruiting communication surface exposes four honest synthetic views and status boundaries", () => {
  const { CommunicationSurface } = loadSource("components/workspace-surfaces.tsx", dependencies);
  const view = CommunicationSurface();
  const content = text(view);
  for (const label of ["连接 BOSS 直聘", "尚未连接", "待处理会话", "执行任务", "定时委托", "结果记录", "合成演示状态", "等待用户", "结果未知", "继续问 Agent"]) assert.match(content, new RegExp(label));
  assert.match(content, /密码、短信验证码和验证码只应由你在安全浏览器中输入/);
  assert.match(content, /不会连接 BOSS、创建后台任务或发送消息/);
  assert.match(content, /普通聊天文本也不会自动成为外部发送授权/);
});
