"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Bird, BriefcaseBusiness, FileText, FolderOpen, LogOut, MessageSquare, UserRound } from "lucide-react";

import { RuntimeProvider } from "@/app/runtime-provider";
import { ProfileEditor } from "@/components/profile-editor";
import { Thread } from "@/components/thread.aui";
import { Button } from "@/components/ui/button";
import { authClient } from "@/lib/auth-client";

const upcoming = [
  { icon: BriefcaseBusiness, label: "岗位" },
  { icon: FolderOpen, label: "申请" },
  { icon: FileText, label: "材料" },
];

function AgentWelcome() {
  return <div className="space-y-2 px-4 text-center"><h2 className="font-semibold">一起想清楚下一步</h2><p className="text-sm text-muted-foreground">当前对话尚未接入职业档案，也不会自动修改档案。刷新后对话暂不恢复。</p></div>;
}

export function WorkspaceShell() {
  const router = useRouter();
  const [agentOpen, setAgentOpen] = useState(false);
  const [agentMounted, setAgentMounted] = useState(false);
  const [signOutError, setSignOutError] = useState("");

  async function signOut() {
    if (!window.confirm("确定退出登录？请先保存职业档案中的修改。")) return;
    try {
      const result = await authClient.signOut();
      if (result.error) { setSignOutError("退出失败，请重试。"); return; }
      router.replace("/sign-in");
      router.refresh();
    } catch { setSignOutError("退出失败，请重试。"); }
  }

  return (
    <div className="min-h-dvh bg-muted/25 lg:grid lg:grid-cols-[14rem_minmax(0,1fr)]">
      <aside className="border-b bg-background p-5 lg:sticky lg:top-0 lg:flex lg:h-dvh lg:flex-col lg:border-r lg:border-b-0">
        <a href="#profile" className="flex items-center gap-2 text-xl font-semibold tracking-tight"><Bird className="size-7" />CareerAct</a>
        <p className="mt-2 text-xs text-muted-foreground">你的个人职业 Agent</p>
        <nav aria-label="工作台导航" className="mt-6 flex flex-wrap gap-2 lg:flex-col">
          <a href="#profile" aria-current="page" className="flex items-center gap-2 rounded-md bg-foreground px-3 py-2.5 text-sm font-medium text-background"><UserRound className="size-4" />职业档案</a>
          {upcoming.map(({ icon: Icon, label }) => <span key={label} className="flex items-center gap-2 px-3 py-2.5 text-sm text-muted-foreground"><Icon className="size-4" />{label}<span className="ml-auto text-[10px]">待开放</span></span>)}
        </nav>
        <div className="mt-6 lg:mt-auto">
          <p className="mb-4 hidden text-xs leading-5 text-muted-foreground lg:block">从已确认的职业事实出发，逐步完善材料与求职行动。</p>
          {signOutError && <p role="alert" className="mb-2 text-xs text-destructive">{signOutError}</p>}
          <Button variant="ghost" size="sm" onClick={signOut}><LogOut className="size-4" />退出登录</Button>
        </div>
      </aside>
      <main id="profile" className="min-w-0">
        <header className="flex items-center justify-between gap-4 border-b bg-background px-5 py-4 sm:px-8">
          <p className="text-sm text-muted-foreground">我的工作台 <span className="mx-2">/</span><span className="text-foreground">职业档案</span></p>
          <Button variant="outline" size="sm" onClick={() => { setAgentMounted(true); setAgentOpen(!agentOpen); }} aria-expanded={agentOpen} aria-controls="career-agent"><MessageSquare className="size-4" />{agentOpen ? "收起 Agent" : "打开 Agent"}</Button>
        </header>
        <div className={agentOpen ? "xl:grid xl:grid-cols-[minmax(0,1fr)_23rem]" : ""}>
          <div className="mx-auto w-full max-w-4xl space-y-7 px-5 py-8 sm:px-8">
            <div><p className="mb-2 text-xs font-medium tracking-widest text-muted-foreground">CAREER PROFILE</p><h1 className="text-3xl font-semibold tracking-tight">你的经历，值得持续积累。</h1><p className="mt-3 text-sm leading-6 text-muted-foreground">把教育、经历、能力和目标整理在一起，建立属于你的职业档案。</p></div>
            <ProfileEditor />
          </div>
          {agentMounted && <aside id="career-agent" aria-label="职业 Agent" className={agentOpen ? "h-[38rem] min-w-0 border-t bg-background xl:sticky xl:top-0 xl:h-[calc(100dvh-4rem)] xl:border-t-0 xl:border-l" : "hidden"}><RuntimeProvider><Thread autoFocus={false} components={{ Welcome: AgentWelcome }} /></RuntimeProvider></aside>}
        </div>
      </main>
    </div>
  );
}
