export type ProfileEntry = {
  title: string;
  organization: string;
  period: string;
  details: string;
  evidence: string;
};

export type ProfileContent = {
  display_name: string;
  education: ProfileEntry[];
  experience: ProfileEntry[];
  projects: ProfileEntry[];
  skills: string;
  goals: string;
  constraints: string;
};

export type CareerProfile = {
  content: ProfileContent;
  version: string | null;
  confirmed_at: string | null;
};

export const profileSections = [
  { key: "education", label: "教育背景", titleLabel: "专业与学位", organizationLabel: "学校" },
  { key: "experience", label: "工作与实习", titleLabel: "职位", organizationLabel: "公司或组织" },
  { key: "projects", label: "项目与成果", titleLabel: "项目或成果名称", organizationLabel: "角色或所属组织" },
] as const;
