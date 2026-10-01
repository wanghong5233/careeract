"use client";

import { useId, useState, type ReactNode } from "react";
import Link from "next/link";
import { ArrowRight, Bird, Check, ChevronRight, LockKeyhole, PanelTop, Search } from "lucide-react";

import { AgentAction } from "@/components/workspace-actions";
import { Button } from "@/components/ui/button";
import { navigationHref, workspaceSections, type WorkspaceSection } from "@/components/workspace-sections";
import { WorkspaceProjects } from "@/components/workspace-projects";
import { cn } from "@/lib/utils";

function SurfaceHeader({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <header className="mb-7 flex flex-wrap items-start justify-between gap-4"><div className="max-w-2xl"><h1 className="text-2xl font-semibold tracking-tight">{title}</h1><p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p></div>{action}</header>;
}

function Unavailable({ children }: { children: ReactNode }) {
  return <p role="note" className="mb-5 flex items-start gap-2 rounded-lg bg-muted/60 px-3 py-2.5 text-xs leading-5 text-muted-foreground"><LockKeyhole className="mt-0.5 size-3.5 shrink-0" />{children}</p>;
}

function EmptyWork({ title, description, children }: { title: string; description: string; children?: ReactNode }) {
  return <div className="flex min-h-64 flex-col items-center justify-center px-5 py-10 text-center"><PanelTop className="mb-4 size-6 text-muted-foreground" /><h2 className="text-base font-medium">{title}</h2><p className="mt-2 max-w-sm text-sm leading-6 text-muted-foreground">{description}</p>{children && <div className="mt-5 flex flex-wrap justify-center gap-2">{children}</div>}</div>;
}

function ViewPicker({ options, value, onChange, label }: { options: readonly string[]; value: string; onChange: (value: string) => void; label: string }) {
  return <div role="group" aria-label={label} className="flex flex-wrap gap-1">{options.map(option => <button key={option} aria-pressed={value === option} onClick={() => onChange(option)} className={cn("min-h-9 rounded-md px-3 text-xs outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring", value === option ? "bg-muted font-medium" : "text-muted-foreground hover:bg-muted/50")}>{option}</button>)}</div>;
}

function RelatedWork({ sections }: { sections: WorkspaceSection[] }) {
  return <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-3 border-t pt-4"><span className="text-xs text-muted-foreground">相关工作</span>{sections.map(key => { const item = workspaceSections.find(candidate => candidate.key === key)!; return <Link key={key} href={navigationHref(key)} className="inline-flex items-center gap-1 text-xs underline underline-offset-4">{item.label}<ChevronRight className="size-3" /></Link>; })}</div>;
}

type RecordSection = "opportunities" | "applications" | "inbox" | "tasks" | "reports";
type RecordSurfaceDefinition = {
  description: string; filters: string[]; placeholder: string; columns: string[];
  empty: string; boundary: string; detail: string; fields: string[]; prompt: string;
  related: WorkspaceSection[];
};

const recordSurfaces: Record<RecordSection, RecordSurfaceDefinition> = {
  opportunities: {
    description: "先看一手来源，再结合目标、约束和申请历史判断是否值得行动。",
    filters: ["值得核验", "关注名单", "待核实", "暂不考虑"], placeholder: "公司、职位编号或岗位方向", columns: ["公司 / 岗位", "来源与变化", "判断", "下一步"],
    empty: "等待第一条有来源的机会", boundary: "岗位获取与检索尚未接入。当前筛选不会搜索互联网。", detail: "岗位依据", fields: ["官方来源与核验时间", "JD、编号、城市与通道", "匹配事实与未知项", "申请额度与跳过理由"],
    prompt: "我想讨论如何寻找适合我的岗位。请先确认目标和约束，给我一手来源的研究方向；不要声称已经搜索网站。", related: ["applications", "automations", "background"],
  },
  applications: {
    description: "当前状态、观察记录和下一步分开保存；准备时始终能找到实际投出的版本。",
    filters: ["全部申请", "进行中", "需要跟进", "额度与志愿"], placeholder: "公司、岗位、编号或批次", columns: ["公司 / 岗位", "批次与渠道", "当前阶段", "下一步"],
    empty: "在这里找回每一次申请", boundary: "申请记录尚未接入，不能将当前页面视为已核对的投递总表。", detail: "申请档案", fields: ["申请编号与渠道", "当前状态与冲突来源", "实投材料快照", "沟通、测评和变更历史"],
    prompt: "我想理清某家公司的申请情况。我会提供记录，请区分已确认状态、通知中的观察和待核实信息，再讨论下一步。", related: ["library", "calendar", "preparation", "execution"],
  },
  inbox: {
    description: "通知关联申请，回复依据事实。涉及时间承诺或未知问题，先带回给你决定。",
    filters: ["需要我处理", "全部沟通", "招聘通知", "主动触达"], placeholder: "招聘方、公司或通知内容", columns: ["公司 / 会话", "最近内容", "待确认事项"],
    empty: "让分散的招聘沟通回到同一处", boundary: "招聘平台与通知源尚未连接，发送、附件和自动回复均未开放。", detail: "回复与依据", fields: ["关联岗位与申请", "原始消息及时间", "回复草稿与事实来源", "授权范围和发送结果"],
    prompt: "我会粘贴一条招聘消息，请帮我理解意图并起草回复。事实不足和时间承诺先问我，不要发送消息。", related: ["applications", "calendar", "automations"],
  },
  tasks: {
    description: "每项工作有自己的结果与状态。等待你处理、失败和外部结果未知必须分开。",
    filters: ["全部工作", "正在推进", "等待我", "异常与结束"], placeholder: "工作名称或关联对象", columns: ["工作与对象", "业务状态", "结果 / 下一步"],
    empty: "工作会带着结果回到这里", boundary: "职业任务尚未接入。对话响应不等于后台任务，关闭页面后续跑尚未开放。", detail: "工作交接", fields: ["目标、范围与上下文版本", "当前状态和需要你做的事", "成果、来源与结果证据", "暂停、取消及恢复条件"],
    prompt: "我想把一个职业目标拆成可验收的工作。请先确认目标、输入、完成标准和需要我决定的事项。", related: ["assistant", "reports", "automations"],
  },
  reports: {
    description: "看做了什么、结果如何、还需处理什么；重要动作能回到当时的授权和证据。",
    filters: ["全部结果", "已完成", "需处理", "操作记录"], placeholder: "公司、工作或结果内容", columns: ["结果与工作", "结果分类", "证据 / 待处理"],
    empty: "成果与结果证据会留在这里", boundary: "报告数据尚未接入，没有可认定为成功的外部执行记录。", detail: "结果核验", fields: ["完成、部分完成、跳过或失败", "未知结果与人工对账", "材料版本和授权", "尝试记录与确定性证据"],
    prompt: "我会提供一次求职行动的结果，请帮我整理已完成、跳过、失败、未知和下一步，不能把不确定的结果写成成功。", related: ["tasks", "applications", "execution"],
  },
};

function RecordSurface({ section }: { section: RecordSection }) {
  const definition = recordSurfaces[section];
  const [filter, setFilter] = useState(definition.filters[0]);
  const [query, setQuery] = useState("");
  return <>
    <SurfaceHeader title={workspaceSections.find(item => item.key === section)!.label} description={definition.description} action={<AgentAction prompt={definition.prompt}>与伙伴讨论</AgentAction>} />
    <Unavailable>{definition.boundary}</Unavailable>
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><ViewPicker options={definition.filters} value={filter} onChange={setFilter} label="记录视图" /><label className="flex h-9 max-w-full items-center gap-2 rounded-md border px-3"><Search className="size-3.5 shrink-0 text-muted-foreground" /><input aria-label={definition.placeholder} placeholder={definition.placeholder} value={query} onChange={event => setQuery(event.target.value)} className="min-w-0 w-48 bg-transparent text-xs outline-none" /></label></div>
    <div className="grid min-w-0 gap-6 2xl:grid-cols-[minmax(0,1fr)_16rem]">
      <div className="min-w-0 overflow-hidden rounded-xl border"><div className="overflow-x-auto"><table className="w-full min-w-96 text-left text-xs"><caption className="sr-only">{filter}；{definition.boundary}</caption><thead className="border-b bg-muted/30 text-muted-foreground"><tr>{definition.columns.map(column => <th key={column} className="px-4 py-3 font-normal">{column}</th>)}</tr></thead></table></div><EmptyWork title={definition.empty} description={query ? "数据源尚未接入，暂时不能核对“" + query + "”的记录。" : "当前查看：" + filter + "。接入记录后，从这里选择对象，查看依据、历史和下一步。"} /></div>
      <aside className="rounded-xl border p-5"><h2 className="text-sm font-medium">{definition.detail}</h2><p className="mt-2 text-xs leading-5 text-muted-foreground">选择记录后查看</p><ul className="mt-5 space-y-4">{definition.fields.map(field => <li key={field} className="flex items-start gap-2 text-xs leading-5 text-muted-foreground"><span className="mt-2 size-1 shrink-0 rounded-full bg-muted-foreground/50" />{field}</li>)}</ul></aside>
    </div>
    <RelatedWork sections={definition.related} />
  </>;
}

type ContentSection = "library" | "growth" | "preparation" | "practice";
const contentSurfaces: Record<ContentSection, { description: string; folders: string[]; empty: string; outcome: string; prompt: string; related: WorkspaceSection[] }> = {
  library: { description: "原件、事实和对外表达各有位置；让伙伴创作，你审阅同一份成果。", folders: ["全部资料", "申请材料", "经历素材", "研究与笔记", "原始来源"], empty: "选择一份共同打磨的内容", outcome: "正文、来源、修改提议与历史版本会在同一工作面切换。", prompt: "我想打磨一份职业材料。我会提供正文、真实事实和用途，请先确认边界，再提出修改，不编造经历。", related: ["background", "review", "applications"] },
  growth: { description: "把工作和学习中的证据积累下来，再复用于下一次申请、面试与职业选择。", folders: ["经历与成果", "能力账本", "待补能力", "阶段复盘"], empty: "把一段新经历留成长期资产", outcome: "原始职责、难题、证据与可迁移能力关联保存，不只剩下一条简历表达。", prompt: "我想复盘一段实习或工作经历。我会讲述职责、难题和结果，请帮我提取已确认事实、能力证据与待核实内容。", related: ["background", "library", "projects"] },
  preparation: { description: "围绕具体岗位和实投版本准备，把公司研究、面经与训练连成下一步。", folders: ["准备计划", "公司研究", "面经整理", "算法与知识", "练习与复测"], empty: "从下一场真实挑战开始", outcome: "准备材料关联公司、岗位、轮次和实投版本；原始回答与事后补强分别保留。", prompt: "我想准备一场笔试或面试。请先问我公司、岗位、轮次、已投材料和准备时间，再一起制定计划。", related: ["applications", "practice", "interviews", "calendar"] },
  practice: { description: "围绕真实项目讲清职责、判断和结果，让反馈回到经历证据与下一次练习。", folders: ["项目讲述", "实习讲述", "追问与攻防", "练习反馈"], empty: "和伙伴练习一段经历", outcome: "讲述稿、事实依据、追问和反馈一起维护；不能用表达包装替代真实能力。", prompt: "我想练习讲述一个真实项目。请先让我介绍事实和职责，再围绕技术选择、难题与结果追问并反馈。", related: ["growth", "library", "preparation", "interviews"] },
};

function ContentSurface({ section }: { section: ContentSection }) {
  const definition = contentSurfaces[section];
  const [folder, setFolder] = useState(definition.folders[0]);
  const [mode, setMode] = useState("正文");
  return <>
    <SurfaceHeader title={workspaceSections.find(item => item.key === section)!.label} description={definition.description} action={<AgentAction prompt={definition.prompt}>告诉伙伴你的想法</AgentAction>} />
    <Unavailable>内容、来源和版本尚未接入。当前可以讨论，不能上传、保存、导出或接受修改。</Unavailable>
    <div className="grid min-h-96 overflow-hidden rounded-xl border md:grid-cols-[10.5rem_minmax(0,1fr)]">
      <nav aria-label="内容分类" className="flex flex-wrap gap-1 border-b bg-muted/20 p-3 md:flex-col md:justify-start md:border-b-0 md:border-r">{definition.folders.map(item => <button key={item} onClick={() => setFolder(item)} aria-pressed={folder === item} className={cn("min-h-9 rounded-md px-3 text-left text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring", folder === item ? "bg-muted font-medium" : "text-muted-foreground hover:bg-muted/60")}>{item}</button>)}</nav>
      <section className="min-w-0"><div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2"><span className="text-xs text-muted-foreground">{folder}</span><ViewPicker options={["正文", "来源", "版本"]} value={mode} onChange={setMode} label="内容工作模式" /></div><EmptyWork title={mode === "正文" ? definition.empty : mode === "来源" ? "来源与事实依据" : "每次修改保留自己的版本"} description={mode === "正文" ? definition.outcome : mode === "来源" ? "尚未选择内容。接入后可以核对原件、事实和引用，待确认的信息不会自动成为事实。" : "尚未选择内容。历史申请锁定当时版本；后续改写不会覆盖实际投出的材料。"}><AgentAction variant="outline" prompt={definition.prompt}>从一次讨论开始</AgentAction></EmptyWork></section>
    </div>
    <RelatedWork sections={definition.related} />
  </>;
}

function ProjectSurface() {
  return <>
    <WorkspaceProjects />
    <RelatedWork sections={["background", "growth", "tasks", "decisions"]} />
  </>;
}

function ReviewSurface() {
  const [view, setView] = useState("改动");
  return <>
    <SurfaceHeader title="材料审阅" description="伙伴负责改写，你用反馈继续打磨，再决定是否接受这一版。接受修改不等于授权投递。" />
    <Unavailable>材料修改提议尚未接入。当前没有可接受或拒绝的真实 Diff。</Unavailable>
    <div className="overflow-hidden rounded-xl border"><div className="flex flex-wrap items-center justify-between gap-2 border-b p-3"><ViewPicker options={["改动", "全文", "版本"]} value={view} onChange={setView} label="材料审阅模式" /><span className="text-xs text-muted-foreground">尚未选择材料</span></div>
      {view === "改动" ? <div className="grid sm:grid-cols-2"><div className="border-b p-5 sm:border-b-0 sm:border-r"><h2 className="text-xs text-muted-foreground">当前确认版本</h2><EmptyWork title="原文" description="选择材料后查看修改前的正文。" /></div><div className="p-5"><h2 className="text-xs text-muted-foreground">伙伴修改提议</h2><EmptyWork title="待审阅改动" description="新增、删除、理由和事实依据在这里核对。" /></div></div> : <EmptyWork title={view === "全文" ? "在完整正文中审阅" : "核对修改来源与历史版本"} description="先在资料与成果中选择材料，再带着同一版本进入审阅。" />}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t px-5 py-4"><p className="text-xs text-muted-foreground">没有提议，暂不能接受或保存</p><div className="flex gap-2"><Button variant="outline" disabled>拒绝修改</Button><Button disabled><Check className="size-4" />接受这一版</Button></div></div>
    </div>
    <RelatedWork sections={["library", "background", "execution"]} />
  </>;
}

function ExecutionSurface() {
  return <>
    <SurfaceHeader title="申请执行" description="找到当次岗位申请，填写后读回核验，再按授权提交；结果未知时交给人工对账。" />
    <Unavailable>申请任务、浏览器会话和产品授权尚未接入，不能执行真实填表或投递。</Unavailable>
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_17rem]"><section className="overflow-hidden rounded-xl border"><div className="flex flex-wrap gap-x-5 gap-y-3 border-b px-5 py-4">{["确认岗位", "填写与保存", "读取核验", "授权提交", "结果证据"].map((step, index) => <span key={step} className="text-xs text-muted-foreground">{index + 1}. {step}</span>)}</div><EmptyWork title="没有正在执行的申请" description="申请任务会在这里显示岗位身份、填写核对、浏览器接管与最终回执。" /><div className="border-t px-5 py-4 text-xs leading-5 text-muted-foreground">登录、验证码、未知字段或风控需要人工介入；外部结果不确定时不能自动重试。</div></section><aside className="rounded-xl border p-5"><h2 className="text-sm font-medium">本次动作边界</h2><dl className="mt-5 space-y-4 text-xs">{["公司与职位编号", "渠道与当次申请", "锁定材料版本", "授权动作与有效期", "核验结果与回执"].map(label => <div key={label}><dt className="text-muted-foreground">{label}</dt><dd className="mt-1">尚未提供</dd></div>)}</dl><Button disabled className="mt-6 w-full">核验后授权提交</Button></aside></div>
    <RelatedWork sections={["applications", "library", "tasks", "reports"]} />
  </>;
}

function CalendarSurface() {
  const [view, setView] = useState("即将到来");
  return <><SurfaceHeader title="日程与提醒" description="同一场测评可以关联多个申请；完成日程与招聘阶段分别记录。" /><Unavailable>日程与提醒尚未接入，不会发送提醒或创建外部日历事件。</Unavailable><ViewPicker options={["即将到来", "待确认时间", "已完成"]} value={view} onChange={setView} label="日程视图" /><div className="mt-5 overflow-hidden rounded-xl border"><div className="flex flex-wrap gap-6 border-b px-5 py-3 text-xs text-muted-foreground"><span>时间与时区</span><span>测评 / 面试 / 截止</span><span>关联申请</span><span>来源与确认</span></div><EmptyWork title={view === "待确认时间" ? "需要承诺的时间先由你决定" : view === "已完成" ? "完成记录保留与申请的关系" : "为下一件重要的事留出时间"} description="从招聘通知中确认日期、场次和材料；提醒只能基于已确认的安排。" /></div><RelatedWork sections={["inbox", "applications", "preparation"]} /></>;
}

function DecisionSurface() {
  return <><SurfaceHeader title="职业决策" description="伙伴整理依据与取舍，最后的选择属于你。保留当时的目标、约束和理由。" action={<AgentAction prompt="我想比较几个职业机会。请先问我长期目标、硬约束、可确认的信息和不确定性，整理取舍；最终由我决定。">讨论一次选择</AgentAction>} /><Unavailable>机会比较与决定记录尚未接入，当前讨论不会保存或对外接受、拒绝 Offer。</Unavailable><div className="rounded-xl border"><div className="flex flex-wrap gap-5 border-b px-5 py-4 text-xs text-muted-foreground">{["发展方向", "职责与能力", "城市与约束", "待遇与时间", "未知与风险"].map(label => <span key={label}>{label}</span>)}</div><EmptyWork title="比较之前，先明确什么对你重要" description="把岗位判断、Offer 与长期目标放在一起；区分事实、分析、伙伴建议和你的决定。" /></div><RelatedWork sections={["projects", "opportunities", "growth"]} /></>;
}

function InterviewSurface() {
  const [language, setLanguage] = useState("中文");
  const [mode, setMode] = useState("文字");
  return <><SurfaceHeader title="模拟面试" description="围绕实投版本和真实岗位连续追问，结束后将反馈与薄弱项带回准备计划。" /><Unavailable>正式模拟面试、评测与实时语音尚未接入。选择模式不会开启麦克风或创建训练任务。</Unavailable><div className="grid gap-6 xl:grid-cols-[15rem_minmax(0,1fr)]"><aside className="rounded-xl border p-5"><h2 className="text-sm font-medium">本次准备</h2><p className="mb-2 mt-5 text-xs text-muted-foreground">语言</p><ViewPicker options={["中文", "English"]} value={language} onChange={setLanguage} label="面试语言" /><p className="mb-2 mt-5 text-xs text-muted-foreground">方式</p><ViewPicker options={["文字", "实时语音"]} value={mode} onChange={setMode} label="面试方式" /><p className="mt-5 text-xs leading-6 text-muted-foreground">尚未选择岗位、实投版本与面试轮次</p><Button disabled className="mt-5 w-full">开始模拟面试</Button></aside><section className="rounded-xl border"><EmptyWork title="一场有上下文的练习" description={"当前选择：" + language + " · " + mode + "。问题、追问与反馈基于同一组材料，原始回答与事后补强分别保存。"} /><div className="border-t p-5 text-xs text-muted-foreground">结束后：反馈 → 薄弱项 → 下一次准备与复测</div></section></div><RelatedWork sections={["applications", "preparation", "practice"]} /></>;
}

function PartnerSurface() {
  const [view, setView] = useState("共同工作");
  return <><SurfaceHeader title="渡鸦 · 职业伙伴" description="围绕同一份职业背景持续协作。记住什么、依据什么、完成什么、什么时候需要你，都应该能核对。" action={<AgentAction>打开伙伴对话</AgentAction>} /><Unavailable>当前仅接通用对话；长期规则、职业读取工具、工作记录与刷新恢复尚未接入。</Unavailable><ViewPicker options={["共同工作", "背景与规则", "持续职责"]} value={view} onChange={setView} label="伙伴工作视图" /><div className="mt-5 rounded-xl border"><div className="flex items-center gap-3 border-b px-5 py-4"><Bird className="size-5" /><div><h2 className="text-sm font-medium">协作从你的目标开始</h2><p className="mt-1 text-xs text-muted-foreground">待命不表示正在后台运行</p></div></div><EmptyWork title={view === "共同工作" ? "给出想法，审阅伙伴带回的成果" : view === "背景与规则" ? "可纠正、有来源的长期上下文" : "持续职责需要独立的范围与授权"} description={view === "共同工作" ? "创作、反馈、再修改和审阅围绕同一对象展开；对话只是协作入口。" : view === "背景与规则" ? "已确认事实、目标、约束、注意事项与个人决定分别维护。伙伴推断先作为提议，确认后才生效。" : "一次工作不会自动变成托管；频率、到期、允许动作和暂停状态始终可以查看。"} /></div><RelatedWork sections={view === "背景与规则" ? ["background", "projects", "growth"] : ["tasks", "automations", "reports"]} /></>;
}

function AutomationSurface() {
  const [duty, setDuty] = useState("岗位关注");
  return <><SurfaceHeader title="托管服务" description="把一项持续职责交给伙伴，随时查看范围、暂停或撤销；一次委托不等于长期授权。" /><Unavailable>调度和托管策略尚未接入。当前没有运行中的服务，所有对外写动作关闭。</Unavailable><ViewPicker options={["岗位关注", "消息值班", "通知整理"]} value={duty} onChange={setDuty} label="持续职责类型" /><div className="mt-5 grid gap-6 xl:grid-cols-[minmax(0,1fr)_18rem]"><section className="rounded-xl border"><EmptyWork title={"为“" + duty + "”先划定职责"} description="指定公司、平台或授权信息源，确认筛选规则、巡检频率、数量上限与到期时间，再开启持续服务。" /><div className="border-t px-5 py-4 text-xs leading-6 text-muted-foreground">验证码、风控、事实不足和时间承诺会暂停相应动作并带回用户处理；未知发送结果不能重发。</div></section><aside className="rounded-xl border p-5"><h2 className="text-sm font-medium">授权摘要</h2><dl className="mt-5 space-y-4 text-xs">{["来源与岗位范围", "规则与材料版本", "频率、数量与有效期"].map(label => <div key={label}><dt className="text-muted-foreground">{label}</dt><dd className="mt-1">尚未设定</dd></div>)}</dl><div className="mt-5 border-t pt-4 text-xs leading-6"><p>对外提交 · 关闭</p><p>发送材料 · 关闭</p><p>对外回复 · 关闭</p></div><Button disabled className="mt-5 w-full">审阅并开启服务</Button></aside></div><RelatedWork sections={["assistant", "opportunities", "inbox", "reports"]} /></>;
}

function SettingsSurface() {
  const [view, setView] = useState("账户");
  const identity = useId();
  return <><SurfaceHeader title="设置与连接" description="产品账户、模型来源和授权连接各有边界；切换模型不应要求重新搬运职业背景。" /><ViewPicker options={["账户", "模型与用量", "来源连接", "我的数据"]} value={view} onChange={setView} label="设置分类" /><section className="mt-5 max-w-3xl divide-y rounded-xl border"><div className="p-5"><h2 className="text-sm font-medium">{view}</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">{view === "账户" ? "当前已使用产品账户登录。框架运维管理和模型网关凭据不赋予产品管理权限。" : view === "模型与用量" ? "服务端模型通过统一网关接入。用户独立额度、BYOK 管理与加密存储尚未开放。" : view === "来源连接" ? "仅接入经你授权的招聘网站、平台或通知源；可以查看范围并撤销。" : "资料与职业记录按产品身份隔离。导出、删除和恢复流程尚未开放。"}</p></div><div className="space-y-4 p-5">{view === "模型与用量" ? <><label htmlFor={identity} className="block text-xs text-muted-foreground">个人模型密钥</label><input id={identity} disabled type="password" placeholder="凭据管理尚未开放，请勿在对话中输入密钥" className="h-10 w-full rounded-md border px-3 text-xs" /><Button disabled variant="outline">连接模型服务</Button></> : view === "来源连接" ? <><p className="text-xs text-muted-foreground">官网、BOSS 直聘、猎聘、授权通知 · 均未连接</p><Button disabled variant="outline">添加授权连接</Button></> : view === "我的数据" ? <><p className="text-xs text-muted-foreground">数据管理操作尚未接入</p><div className="flex gap-2"><Button disabled variant="outline">导出我的数据</Button><Button disabled variant="outline">删除数据</Button></div></> : <><p className="text-xs text-muted-foreground">登录与退出可用；资料访问始终由服务端校验归属。</p><Link href="/workspace/background" className="inline-flex items-center gap-1 text-sm underline underline-offset-4">查看我的职业背景<ArrowRight className="size-3.5" /></Link></>}</div></section></>;
}

export function WorkspaceSurface({ section }: { section: WorkspaceSection }) {
  if (section in recordSurfaces) return <RecordSurface key={section} section={section as RecordSection} />;
  if (section in contentSurfaces) return <ContentSurface key={section} section={section as ContentSection} />;
  switch (section) {
    case "projects": return <ProjectSurface />;
    case "review": return <ReviewSurface />;
    case "execution": return <ExecutionSurface />;
    case "calendar": return <CalendarSurface />;
    case "decisions": return <DecisionSurface />;
    case "interviews": return <InterviewSurface />;
    case "assistant": return <PartnerSurface />;
    case "automations": return <AutomationSurface />;
    case "settings": return <SettingsSurface />;
    default: return null;
  }
}
