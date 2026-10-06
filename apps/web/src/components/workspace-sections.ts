import {
  Archive,
  Command,
  BookOpen,
  CalendarDays,
  CheckSquare,
  FileText,
  FolderKanban,
  Inbox,
  Layers3,
  MessageSquare,
  Radar,
  Route,
  Settings2,
  Sparkles,
  Target,
  Timer,
  Workflow,
  type LucideIcon,
} from "lucide-react";

export type WorkspaceSection =
  | "overview" | "projects" | "background" | "library" | "growth"
  | "opportunities" | "applications" | "inbox" | "calendar"
  | "preparation" | "decisions" | "practice" | "interviews"
  | "assistant" | "tasks" | "automations" | "reports" | "settings"
  | "execution" | "review";

export type WorkspaceNavItem = {
  key: WorkspaceSection;
  label: string;
  description: string;
  icon: LucideIcon;
  group: string;
  keywords?: string;
};

export const workspaceGroups = ["Agent", "职业积累", "求职行动", "准备与决策", "系统"];

export function navigationHref(key: WorkspaceSection) {
  return key === "overview" ? "/" : `/${key}`;
}

export const workspaceSections: WorkspaceNavItem[] = [
  { key: "overview", label: "Agent 委托", description: "表达目标与继续工作", icon: Command, group: "Agent" },
  { key: "review", label: "材料审阅", description: "Diff、来源与版本", icon: FileText, group: "Agent" },
  { key: "execution", label: "申请执行", description: "核对、授权与接管", icon: Workflow, group: "Agent" },
  { key: "projects", label: "职业项目", description: "目标、里程碑与复盘", icon: FolderKanban, group: "职业积累" },
  { key: "background", label: "职业背景", description: "事实、来源与证据", icon: Layers3, group: "职业积累" },
  { key: "library", label: "资料与成果", description: "原件、材料与版本", icon: FileText, group: "职业积累", keywords: "简历 实习 经历 文档 导出" },
  { key: "growth", label: "能力与成长", description: "能力账本与工作成果", icon: Route, group: "职业积累" },
  { key: "opportunities", label: "机会发现", description: "岗位来源与判断", icon: Radar, group: "求职行动" },
  { key: "applications", label: "申请追踪", description: "状态、历史与下一步", icon: Inbox, group: "求职行动", keywords: "公司 投递记录 额度 志愿 批次 防重" },
  { key: "inbox", label: "招聘沟通", description: "消息、通知与待确认", icon: MessageSquare, group: "求职行动" },
  { key: "calendar", label: "日程与提醒", description: "测评、面试与时间点", icon: CalendarDays, group: "求职行动" },
  { key: "preparation", label: "准备与训练", description: "研究、面经与刷题", icon: BookOpen, group: "准备与决策", keywords: "公司 算法 力扣 笔试 复测" },
  { key: "decisions", label: "职业决策", description: "选择与理由", icon: Target, group: "准备与决策" },
  { key: "practice", label: "项目讲述", description: "经历表达与反馈", icon: Sparkles, group: "准备与决策" },
  { key: "interviews", label: "模拟面试", description: "文字、语音与复盘", icon: MessageSquare, group: "准备与决策" },
  { key: "assistant", label: "Agent 上下文", description: "记忆、规则与职责", icon: Command, group: "Agent", keywords: "规则 注意事项 长期上下文 约束" },
  { key: "tasks", label: "Agent 工作", description: "进度、等待与异常", icon: CheckSquare, group: "Agent" },
  { key: "automations", label: "持续委托", description: "范围、授权与运行", icon: Timer, group: "Agent" },
  { key: "reports", label: "工作结果", description: "结果、证据与记录", icon: Archive, group: "Agent" },
  { key: "settings", label: "设置与连接", description: "账户、模型与来源", icon: Settings2, group: "系统" },
];
