import Link from "next/link";
import { ArrowRight, FileText, FolderKanban, Layers3 } from "lucide-react";

import { AgentAction, CapabilitiesAction } from "@/components/workspace-actions";
import { WorkspaceHomeProject } from "@/components/workspace-home-project";
import { WorkspaceSurface } from "@/components/workspace-surfaces";
import { workspaceSections, type WorkspaceSection } from "@/components/workspace-sections";

export function WorkspaceHome() {
  return <div className="space-y-9">
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div><p className="mb-2 text-xs text-muted-foreground">个人职业工作区</p><h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">现在，一起推进什么？</h1></div>
      <AgentAction>和职业伙伴开始</AgentAction>
    </div>
    <WorkspaceHomeProject />
    <section aria-labelledby="work-heading"><div className="mb-4 flex items-center justify-between"><h2 id="work-heading" className="text-sm font-medium">共同工作</h2><CapabilitiesAction /></div>
      <div className="divide-y rounded-xl border">
        <StartWork title="把一段经历变成可复用的成果" text="整理事实、打磨表达，再带回材料审阅。" href="/workspace/library" icon={FileText} />
        <StartWork title="理清申请进展与下一步" text="以公司、岗位和实投版本组织状态与历史。" href="/workspace/applications" icon={Layers3} />
        <StartWork title="为下一场面试做好准备" text="把岗位、经历、面经和薄弱项联系起来。" href="/workspace/preparation" icon={FolderKanban} />
      </div>
    </section>
    <section className="grid gap-7 sm:grid-cols-2">
      <div><h2 className="text-sm font-medium">正在推进</h2><p className="mt-3 text-sm leading-6 text-muted-foreground">工作记录尚未接入，暂不能恢复后台任务。</p><Link href="/workspace/tasks" className="mt-3 inline-flex items-center gap-1 text-xs underline underline-offset-4">查看任务工作面<ArrowRight className="size-3" /></Link></div>
      <div><h2 className="text-sm font-medium">需要你决定</h2><p className="mt-3 text-sm leading-6 text-muted-foreground">事实确认、材料修改和外部授权会在各自工作面审阅；当前没有已接入的审批队列。</p><Link href="/workspace/review" className="mt-3 inline-flex items-center gap-1 text-xs underline underline-offset-4">打开材料审阅<ArrowRight className="size-3" /></Link></div>
    </section>
  </div>;
}

function StartWork({ title, text, href, icon: Icon }: { title: string; text: string; href: string; icon: typeof FileText }) {
  return <Link href={href} className="group flex items-center gap-4 px-5 py-5 outline-none hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring"><Icon className="size-5 shrink-0 text-muted-foreground" /><div className="min-w-0 flex-1"><h3 className="text-sm font-medium">{title}</h3><p className="mt-1 text-xs leading-5 text-muted-foreground">{text}</p></div><ArrowRight className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-1" /></Link>;
}

export function WorkspaceSectionPage({ section }: { section: WorkspaceSection }) {
  const item = workspaceSections.find(candidate => candidate.key === section);
  if (!item) return null;
  return <WorkspaceSurface section={section} />;
}
