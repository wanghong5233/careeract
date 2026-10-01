"use client";

import type { ReactNode } from "react";
import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Archive,
  Bird,
  BookOpen,
  BriefcaseBusiness,
  CalendarDays,
  CheckSquare,
  FileText,
  FolderKanban,
  Inbox,
  Layers3,
  LogOut,
  MessageSquare,
  PanelRight,
  Radar,
  Route,
  Settings2,
  Sparkles,
  Target,
  Timer,
  Workflow,
} from "lucide-react";

import { RuntimeProvider } from "@/app/runtime-provider";
import { Thread } from "@/components/thread.aui";
import { Button } from "@/components/ui/button";
import { authClient } from "@/lib/auth-client";

export type WorkspaceSection =
  | "overview" | "projects" | "background" | "library" | "growth"
  | "opportunities" | "applications" | "inbox" | "calendar"
  | "preparation" | "decisions" | "practice" | "interviews"
  | "assistant" | "tasks" | "automations" | "reports" | "settings"
  | "execution" | "review";

type WorkspaceNavItem = {
  key: WorkspaceSection;
  label: string;
  description: string;
  icon: typeof BriefcaseBusiness;
  group: string;
};

export const workspaceSections: WorkspaceNavItem[] = [
  { key: "overview", label: "工作台", description: "当前项目与下一步", icon: BriefcaseBusiness, group: "当前工作" },
  { key: "review", label: "材料审阅", description: "Diff、来源与版本", icon: FileText, group: "当前工作" },
  { key: "execution", label: "申请执行", description: "核对、授权与接管", icon: Workflow, group: "当前工作" },
  { key: "projects", label: "职业项目", description: "目标、里程碑与复盘", icon: FolderKanban, group: "职业积累" },
  { key: "background", label: "职业背景", description: "事实、来源与证据", icon: Layers3, group: "职业积累" },
  { key: "library", label: "资料与成果", description: "原件、材料与版本", icon: FileText, group: "职业积累" },
  { key: "growth", label: "能力与成长", description: "能力账本与工作成果", icon: Route, group: "职业积累" },
  { key: "opportunities", label: "机会发现", description: "岗位来源与判断", icon: Radar, group: "求职行动" },
  { key: "applications", label: "申请追踪", description: "状态、历史与下一步", icon: Inbox, group: "求职行动" },
  { key: "inbox", label: "招聘沟通", description: "消息、通知与待确认", icon: MessageSquare, group: "求职行动" },
  { key: "calendar", label: "日程与提醒", description: "测评、面试与时间点", icon: CalendarDays, group: "求职行动" },
  { key: "preparation", label: "准备与训练", description: "研究、面经与刷题", icon: BookOpen, group: "准备与决策" },
  { key: "decisions", label: "职业决策", description: "选择与理由", icon: Target, group: "准备与决策" },
  { key: "practice", label: "项目讲述", description: "经历表达与反馈", icon: Sparkles, group: "准备与决策" },
  { key: "interviews", label: "模拟面试", description: "文字、语音与复盘", icon: MessageSquare, group: "准备与决策" },
  { key: "assistant", label: "职业伙伴", description: "委托、记忆与职责", icon: Bird, group: "Agent 工作" },
  { key: "tasks", label: "任务中心", description: "进度、等待与异常", icon: CheckSquare, group: "Agent 工作" },
  { key: "automations", label: "托管服务", description: "范围、授权与运行", icon: Timer, group: "Agent 工作" },
  { key: "reports", label: "结果报告", description: "结果、证据与记录", icon: Archive, group: "Agent 工作" },
  { key: "settings", label: "设置与连接", description: "账户、模型与来源", icon: Settings2, group: "系统" },
];

const groupOrder = ["当前工作", "职业积累", "求职行动", "准备与决策", "Agent 工作", "系统"];

function AgentWelcome() {
  return <div className="space-y-2 px-4 text-center"><h2 className="font-semibold">把下一步交给职业伙伴</h2><p className="text-sm leading-6 text-muted-foreground">描述目标、提供反馈或要求查看依据。Agent 的结果会回到对应的职业工作面。</p></div>;
}

function AgentDock({ onClose }: { onClose: () => void }) {
  return <aside id="career-agent" aria-label="职业 Agent" className="flex min-h-[34rem] min-w-0 flex-col border-l bg-background xl:sticky xl:top-0 xl:h-[calc(100dvh-4rem)]"><div className="flex items-center justify-between border-b px-5 py-4"><div className="flex items-center gap-3"><span className="grid size-8 place-items-center rounded-lg bg-muted"><Bird className="size-4" /></span><div><p className="text-sm font-medium">渡鸦 · 职业伙伴</p><p className="text-xs text-muted-foreground">辅助工作台</p></div></div><Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="关闭职业 Agent"><PanelRight className="size-4" /></Button></div><div className="min-h-0 flex-1"><RuntimeProvider><Thread autoFocus={false} components={{ Welcome: AgentWelcome }} /></RuntimeProvider></div></aside>;
}

function navigationHref(key: WorkspaceSection) {
  return key === "overview" ? "/workspace" : `/workspace/${key}`;
}

export function WorkspaceFrame({ children }: Readonly<{ children: ReactNode }>) {
  const pathname = usePathname();
  const router = useRouter();
  const [agentOpen, setAgentOpen] = useState(false);
  const [signOutError, setSignOutError] = useState("");
  const activeKey = pathname === "/workspace" ? "overview" : pathname.split("/").filter(Boolean).at(-1) ?? "overview";
  const current = workspaceSections.find(item => item.key === activeKey) ?? workspaceSections[0];

  async function signOut() {
    if (!window.confirm("确定退出登录？请先保存正在编辑的内容。")) return;
    try {
      const result = await authClient.signOut();
      if (result.error) { setSignOutError("退出失败，请重试。"); return; }
      router.replace("/sign-in");
      router.refresh();
    } catch { setSignOutError("退出失败，请重试。"); }
  }

  return <div className="min-h-dvh bg-muted/25 lg:grid lg:grid-cols-[15rem_minmax(0,1fr)]"><aside className="border-b bg-background p-4 lg:sticky lg:top-0 lg:flex lg:h-dvh lg:flex-col lg:overflow-y-auto lg:border-b-0 lg:border-r"><Link href="/workspace" className="flex items-center gap-2 px-2 py-2 text-lg font-semibold tracking-tight"><Bird className="size-6" />CareerAct</Link><p className="px-2 pt-1 text-xs text-muted-foreground">个人职业工作台</p><nav aria-label="工作台导航" className="mt-7 space-y-6">{groupOrder.map(group => <div key={group}><p className="px-2 text-[11px] font-medium tracking-wider text-muted-foreground">{group}</p><div className="mt-2 flex gap-1 overflow-x-auto lg:block">{workspaceSections.filter(item => item.group === group).map(item => { const Icon = item.icon; const active = item.key === activeKey; return <Link key={item.key} href={navigationHref(item.key)} aria-current={active ? "page" : undefined} className={`flex shrink-0 items-center gap-2 rounded-lg px-2.5 py-2 text-sm transition-colors ${active ? "bg-foreground text-background" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}><Icon className="size-4" /><span>{item.label}</span></Link>; })}</div></div>)}</nav><div className="mt-8 lg:mt-auto"><p className="mb-3 hidden px-2 text-xs leading-5 text-muted-foreground lg:block">Agent 负责推进工作，你保留事实确认、反馈和外部授权。</p>{signOutError && <p role="alert" className="mb-2 px-2 text-xs text-destructive">{signOutError}</p>}<Button variant="ghost" size="sm" onClick={signOut}><LogOut className="size-4" />退出登录</Button></div></aside><main className="min-w-0"><header className="sticky top-0 z-20 flex min-h-16 items-center justify-between gap-4 border-b bg-background/95 px-5 backdrop-blur sm:px-8"><div className="min-w-0"><p className="truncate text-sm text-muted-foreground">职业工作区 <span className="mx-2">/</span><span className="text-foreground">{current.label}</span></p><p className="mt-1 hidden text-xs text-muted-foreground sm:block">当前阶段 · 个人职业发展</p></div><Button variant="outline" size="sm" onClick={() => setAgentOpen(value => !value)} aria-expanded={agentOpen} aria-controls="career-agent"><MessageSquare className="size-4" />{agentOpen ? "收起 Agent" : "打开 Agent"}</Button></header><div className={agentOpen ? "xl:grid xl:grid-cols-[minmax(0,1fr)_24rem]" : ""}><div className="mx-auto w-full max-w-6xl px-5 py-9 sm:px-8 lg:py-12">{children}</div>{agentOpen && <AgentDock onClose={() => setAgentOpen(false)} />}</div></main></div>;
}
