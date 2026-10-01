const iconPaths = {
  raven: '<path d="M4 19 8 10l6-6 4 1 3 4-5-1-1 6-5 5-6 2 4-6" fill="currentColor" stroke="none"/><path d="m9 11 3 3-5 4" stroke="#fff" stroke-width=".8"/><circle cx="16.6" cy="6.4" r=".65" fill="#fff" stroke="none"/>',
  grid: '<rect x="4" y="4" width="6" height="6" rx="1.5"/><rect x="14" y="4" width="6" height="6" rx="1.5"/><rect x="4" y="14" width="6" height="6" rx="1.5"/><rect x="14" y="14" width="6" height="6" rx="1.5"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  file: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M8 13h8M8 17h5"/>',
  arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
  up: '<path d="M12 19V5m-5 5 5-5 5 5"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  circle: '<circle cx="12" cy="12" r="8"/>',
  clock: '<circle cx="12" cy="12" r="8"/><path d="M12 7v5l3 2"/>',
  globe: '<circle cx="12" cy="12" r="8"/><path d="M4 12h16M12 4c5 5 5 11 0 16-5-5-5-11 0-16"/>',
  link: '<path d="m10 7 2-2a5 5 0 0 1 7 7l-2 2M14 17l-2 2a5 5 0 0 1-7-7l2-2m2 5 6-6"/>',
  book: '<path d="M12 6c-3-2-6-2-9-1v14c3-1 6-1 9 1 3-2 6-2 9-1V5c-3-1-6-1-9 1v14"/>',
  target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r=".5"/>',
  layers: '<path d="m3 8 9-5 9 5-9 5zM3 12l9 5 9-5M3 16l9 5 9-5"/>',
  settings: '<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3" fill="var(--rail)"/><circle cx="16" cy="17" r="3" fill="var(--rail)"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4"/>',
  copy: '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
  edit: '<path d="m15 4 5 5-11 11H4v-5zM13 6l5 5"/>',
  pause: '<path d="M8 5v14M16 5v14"/>',
  external: '<path d="M14 4h6v6m0-6-9 9M10 4H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5"/>',
  inbox: '<path d="M4 5h16v14H4zM4 13h4l2 3h4l2-3h4"/>',
};
const icon = (name) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${iconPaths[name] || iconPaths.file}</svg>`;
const escapeText = (value) => String(value).replace(/[&<>"']/g, (character) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
const routes = new Set(['project', 'review', 'opportunities', 'execution', 'practice', 'background', 'portfolio', ...Object.keys(workspacePages)]);
const startingRoute = location.hash.slice(1);
const state = {
  route: routes.has(startingRoute) ? startingRoute : 'project',
  changes: ['pending', 'pending'],
  mode: 'review',
  scenario: 'normal',
  execution: 'ready',
  humanControl: false,
  draft: '',
  profileDraft: '',
  editing: false,
  panelOpen: false,
  taskAdded: false,
};
let toastTimer;
const proposals = [
  {
    title: '让项目经历对应岗位的执行可靠性要求',
    old: '负责 Agent 后端开发，完成工具调用及服务集成。',
    next: '构建面向资料整理的 Agent 工作流，接入工具调用、任务恢复与结果核验；将生成内容保存为可继续编辑的成果。',
    reason: '来源：项目记录 §3；调整表达顺序，没有增加未经证实的性能数字。',
  },
  {
    title: '保留推理与系统能力，不只呈现应用层',
    old: '熟悉 Python，了解模型部署和深度学习。',
    next: '使用 Python 构建 Agent 服务；具备模型推理、部署与评测实践，能够从执行效果、延迟和成本共同分析系统。',
    reason: '来源：职业背景 v3 · 技能与项目证据；不扩大为生产规模经验。',
  },
];
const navButton = (route, label, glyph, extra = '') => `<button class="nav-button ${state.route === route ? 'active' : ''}" data-route="${route}" ${state.route === route ? 'aria-current="page"' : ''}>${icon(glyph)}<span>${label}</span>${extra}</button>`;
const resolved = () => state.changes.every((change) => change !== 'pending');
const pendingCount = () => state.changes.filter((change) => change === 'pending').length;

function sidebar() {
  return `<aside class="sidebar" aria-label="工作区导航">
    <div class="brand row">${icon('raven')}CareerAct<span class="spacer"></span><button class="icon-button mobile-menu" data-action="menu" aria-label="关闭项目导航">${icon('close')}</button></div>
    <button class="nav-button" data-action="new">${icon('plus')}<span>开始一项工作</span></button>
    <button class="nav-button" data-action="search">${icon('search')}<span>查找内容</span><span class="count">⌘ K</span></button>
    <div class="nav-group">
      <div class="nav-label">职业项目</div>
      ${navButton('project', '2027 秋招', 'folder', '<span class="count">2</span>')}
      <div class="nav-sub">
        ${navButton('opportunities', '机会与岗位', 'globe')}
        ${navButton('applications', '申请与进展', 'inbox')}
        ${navButton('preparation', '准备与训练', 'book')}
      </div>
      ${navButton('portfolio', 'Agent 工程作品', 'folder')}
    </div>
    <div class="nav-group">
      <div class="nav-label">待处理</div>
      ${navButton('inbox', '沟通与通知', 'inbox')}
      ${navButton('calendar', '日程与待办', 'clock')}
      ${navButton('tasks', '任务与报告', 'check')}
    </div>
    <div class="nav-group">
      <div class="nav-label">跨项目复用</div>
      ${navButton('background', '我的职业背景', 'layers')}
      ${navButton('library', '资料与成果', 'file')}
      ${navButton('growth', '经历与成长', 'book')}
    </div>
    <div class="sidebar-bottom">
      ${navButton('automations', '托管服务', 'clock')}
      ${navButton('settings', '偏好与连接', 'settings')}
      <div class="account row"><span class="avatar">予</span><span>林予的工作区</span><span class="spacer"></span><small class="muted">个人</small></div>
      <div class="preview-note">交互原型 · 虚构人物与岗位<br>操作仅用于演示，不连接外部服务</div>
    </div>
  </aside>`;
}

function topbar() {
  const names = {project: '2027 秋招', review: '星野 · 申请准备', opportunities: '本周机会调研', execution: '星野 · 申请执行', practice: '项目讲述与面试准备', background: '我的职业背景', portfolio: 'Agent 工程作品', ...workspaceRouteNames};
  const scenarios = [['normal','预览状态'],['empty','空项目'],['save-error','保存失败'],['conflict','版本冲突'],['uncertain','提交结果未知']];
  return `<header class="topbar">
    <button class="icon-button mobile-menu" data-action="menu" aria-label="打开项目导航">${icon('menu')}</button>
    <div class="row breadcrumb"><span class="parent-crumb">${['background','portfolio','growth','library','tasks','inbox','calendar','automations','settings','reports','assistant'].includes(state.route) ? '职业工作区' : '2027 秋招'}</span><span class="parent-crumb">/</span><strong>${names[state.route]}</strong></div>
    <span class="spacer"></span><span class="prototype-label">设计预览</span>
    <select class="preview-select" aria-label="演示状态">${scenarios.map(([value,label])=>`<option value="${value}" ${state.scenario === value ? 'selected' : ''}>${label}</option>`).join('')}</select>
    ${['review','execution','practice','background'].includes(state.route) ? `<button class="icon-button mobile-task-toggle" data-action="panel" aria-label="查看 Agent 工作进度">${icon('raven')}</button>` : ''}
  </header>`;
}

function composer(placeholder, context, compact = false) {
  return `<div class="${compact ? 'panel-composer' : 'project-composer'}"><form class="composer" data-composer>
    <textarea aria-label="给 CareerAct 的任务" placeholder="${placeholder}" rows="2">${escapeText(state.draft)}</textarea>
    <div class="composer-footer row"><button type="button" class="icon-button" data-action="context" aria-label="查看任务上下文">${icon('plus')}</button><button type="button" class="context-chip" data-action="context">${icon('layers')}${context}</button><span class="spacer"></span><button class="send-button" type="submit" aria-label="预览这项委托">${icon('up')}</button></div>
  </form>${compact ? '' : '<div class="composer-hint">说出下一步，也可以直接打开资料继续工作。</div>'}</div>`;
}

function projectPage() {
  if (state.scenario === 'empty') return emptyPage();
  return `<div class="project-page">
    <div class="project-heading row between"><div><div class="eyebrow">职业项目</div><h1>2027 秋招</h1><p class="muted">找到能持续积累 Agent 与系统能力的第一份工作。</p></div><button class="button quiet" data-action="project-context">${icon('layers')}项目背景</button></div>
    <div class="project-meta row"><span>9 月 — 12 月</span><span>上海 · 杭州</span><span>校招正职 / 对口实习</span></div>
    ${projectViews()}
    <section class="brief"><div class="agent-mark">${icon('raven')}</div><div><h2>${resolved() ? '材料已就绪，可以继续下一步。' : '申请材料准备好了，等你看两处修改。'}</h2><p>星野的岗位重视 Agent 执行可靠性。我调整了项目表达，并保留了推理与系统方向的经历。提交申请前，仍由你决定。</p></div></section>
    <section class="focus-task" aria-label="等待审阅的成果"><div class="focus-content"><div class="row"><span class="tag attention">${resolved() ? '材料已审阅' : '待你审阅'}</span><span class="muted" style="font-size:11px">申请准备 · 星野智能</span><span class="spacer"></span><small class="muted">12 分钟前</small></div><h2 class="task-title">为 Agent 研发岗位准备一份有依据的申请</h2><p>材料来自已确认背景与项目记录，没有添加新经历或虚构指标。</p><div class="artifact-line row"><div class="file-symbol">${icon('file')}</div><div><strong>简历 · Agent 工程方向</strong><small>基于 v3 · ${resolved() ? '审阅完成' : '2 处修改建议'} · 关联 3 份资料</small></div><span class="spacer"></span><span class="tag">可编辑</span></div></div><div class="focus-footer row between"><span>当前只准备材料，尚未对外提交</span><button class="button primary" data-route="review">${resolved() ? '打开材料' : '审阅并继续'}${icon('arrow')}</button></div></section>
    <div class="project-lower"><section><div class="row between"><h2 class="section-heading">继续推进</h2><span class="muted" style="font-size:10px">与当前目标相关</span></div>
      <button class="work-row" data-route="opportunities">${icon('globe')}<span><strong>这周还有哪些值得看的机会？</strong><small>3 个候选 · 1 项关键信息待核实</small></span><span class="tag">已整理</span></button>
      <button class="work-row" data-route="practice">${icon('book')}<span><strong>把 Agent 项目讲清楚</strong><small>从实际申请材料出发，准备 3 个技术追问</small></span><span class="tag live">准备中</span></button>
      ${state.taskAdded ? '<button class="work-row" data-route="practice">'+icon('target')+'<span><strong>练习：解释失败恢复与幂等边界</strong><small>来自项目讲述材料 · 已加入当前项目</small></span><span class="tag">待完成</span></button>' : ''}
    </section><aside><h2 class="section-heading">项目随身资料</h2><button class="resource" data-route="background">${icon('layers')}职业背景与事实</button><button class="resource" data-route="review">${icon('file')}简历 · Agent 工程方向</button><button class="resource" data-action="constraints">${icon('target')}目标、城市与选择边界</button><button class="resource" data-action="applications">${icon('inbox')}申请记录与材料版本</button></aside></div>
    ${composer('接下来想推进什么？也可以贴入一个岗位链接…', '2027 秋招 · 已连接职业背景')}
  </div>`;
}

function proposalBlock(index) {
  const proposal = proposals[index];
  const decision = state.changes[index];
  if (state.mode !== 'review' || decision !== 'pending') return `<div class="${decision === 'pending' ? '' : 'proposal-resolved'}"><p>${escapeText(decision === 'rejected' ? proposal.old : proposal.next)}</p>${decision === 'pending' ? '' : `<div class="row between"><span class="tag ${decision === 'accepted' ? 'done' : ''}">${decision === 'accepted' ? '已接受这处修改' : '已保留原文'}</span><button class="text-button" data-action="undo-change" data-index="${index}">撤销</button></div>`}</div>`;
  return `<section class="change" aria-label="修改建议 ${index+1}"><div class="row change-header"><span>修改 ${index+1} / 2</span><span class="spacer"></span><span>表达调整</span></div><p class="change-old"><span class="sr-label">原文：</span>${proposal.old}</p><p class="change-new">${proposal.next}</p><div class="change-reason">${proposal.reason}</div><div class="change-actions row"><button class="button" data-action="accept-change" data-index="${index}">${icon('check')}接受这处</button><button class="button quiet" data-action="reject-change" data-index="${index}">保留原文</button><span class="spacer"></span><button class="text-button" data-action="evidence" data-index="${index}">查看依据 ↗</button></div></section>`;
}

function reviewPage() {
  const failure = state.scenario === 'save-error' ? '<div class="callout error">保存失败。你的审阅仍留在当前页面，可以重试；尚未生成可执行的新版本。<button class="text-button" data-action="recover">重试保存</button></div>' : state.scenario === 'conflict' ? '<div class="callout">背景资料已有新版本，这批建议暂不能合入。先核对变化，再重新生成提议。<button class="text-button" data-action="recover">核对并刷新提议</button></div>' : '';
  return `<div class="task-layout"><section class="task-main"><div class="document-toolbar row"><span class="filename row">${icon('file')}简历 · Agent 工程方向</span><span class="spacer"></span><div class="segmented" aria-label="文档显示方式"><button data-action="mode-review" class="${state.mode === 'review' ? 'selected' : ''}">修改建议${pendingCount() ? ' '+pendingCount() : ''}</button><button data-action="mode-read" class="${state.mode === 'read' ? 'selected' : ''}">阅读</button></div><button class="icon-button" data-action="copy" aria-label="复制纯文本">${icon('copy')}</button></div>
    <article class="document">${failure}<div class="eyebrow">申请材料 / 星野智能 · Agent 研发</div><h1>林予</h1><p class="doc-subtitle">人工智能硕士 · 2027 届 · Agent / 推理系统</p><hr class="rule"><section class="doc-section"><h2>教育背景</h2><div class="row between"><p>南川大学 · 人工智能 · 硕士</p><small>2024.09 — 2027.06</small></div><p class="muted">研究方向：模型推理与智能系统</p></section><section class="doc-section"><h2>项目经历</h2><div class="row between"><p><strong>Atlas · 资料研究 Agent</strong></p><small>2026.03 — 至今</small></div>${proposalBlock(0)}<p>实现来源关联与内容审阅，支持用户查看依据、局部修改和继续整理。</p></section><section class="doc-section"><h2>技术能力</h2>${proposalBlock(1)}</section><p class="view-badge">${state.mode === 'read' && !resolved() ? '预览建议合入后的内容 · 尚未接受' : '当前审阅基于 v3；接受修改只生成材料版本，不授权申请。'}</p></article>
    <div class="review-bottom row"><span class="muted">${resolved() ? '审阅完成 · 示例材料版本 v4' : `${pendingCount()} 处修改待决定 · 不覆盖历史申请版本`}</span><span class="spacer"></span><button class="button" data-action="accept-all" ${resolved() ? 'disabled' : ''}>接受全部</button><button class="button primary" data-action="prepare-execution" ${!resolved() || state.scenario !== 'normal' ? 'disabled' : ''}>准备申请${icon('arrow')}</button></div>
    </section>${agentPanel('review')}</div>`;
}

function agentPanel(kind) {
  const configurations = {
    review: {title:'准备星野的申请材料',status:resolved()?'材料已审阅':'等待你的审阅',intro:'我将岗位要求和你的已确认经历放在一起核对，提出两处表达调整。你可以直接修改正文，也可以继续提出要求。',steps:['核对岗位与职业目标','读取已确认背景和项目证据','形成 2 处材料修改建议','等你审阅，再进入申请准备'],context:'这份材料 · 3 份来源',prompt:'例如：保留更多推理部署细节…'},
    execution: {title:'完成星野的岗位申请',status:state.execution === 'completed'?'执行结果已核验':state.execution === 'uncertain'?'结果需要核实':state.execution === 'cancelled'?'已取消':state.humanControl?'你正在接管':'等待提交授权',intro:state.execution === 'uncertain'?'提交已尝试，尚无可靠结果。保留证据并先核对申请记录，不重新提交。':state.execution === 'cancelled'?'任务已取消，尚未提交；材料仍可继续使用。':state.execution === 'completed'?'申请回执已关联材料版本。下一步准备会沿用这次实际提交的内容。':'当前申请表已经准备好。只对这一岗位、这一材料版本执行；确认前不会对外提交。',steps:['检查岗位与重复申请','锁定本次材料 v4','填写后重新读取申请预览','等待提交授权与结果核验'],context:'星野申请 · 材料 v4',prompt:'补充要求，或讨论下一步…'},
    practice: {title:'准备一场有依据的技术面试',status:'准备中',intro:'从实际申请材料出发，把经历拆成问题、证据和可练习的表达。已有结论会沉淀回这个职业项目。',steps:['读取申请锁定版本','对应岗位的技术重点','整理讲述提纲和追问','把薄弱项加入准备任务'],context:'申请材料 v4 · 项目记录',prompt:'让我试着回答第一个追问…'},
    background: {title:'让经历持续成为可用的背景',status:'资料已连接',intro:'你可以贴入经历、导入资料，或直接编辑内容。新事实先作为待确认内容，不会直接进入正式申请。',steps:['保留原始资料与来源','区分事实和对外表达','由你确认新增事实','在相关项目中持续复用'],context:'职业背景 · 事实与来源',prompt:'补充一段经历，或贴入已有资料…'},
  };
  const configuration = configurations[kind];
  return `<aside class="task-panel ${state.panelOpen ? 'open' : ''}" aria-label="Agent 工作详情"><div class="row panel-title">${icon('raven')}CareerAct<span class="spacer"></span><button class="icon-button mobile-task-toggle" data-action="panel" aria-label="收起 Agent 详情">${icon('close')}</button></div><span class="tag ${kind === 'execution' && state.execution === 'completed' ? 'done' : 'attention'}" style="align-self:flex-start">${configuration.status}</span><h2>${configuration.title}</h2><p class="panel-intro">${configuration.intro}</p><div class="mini-heading">工作进度</div>${configuration.steps.map((step,index)=>`<div class="step ${index===3?'current':''}">${icon(index<3?'check':'circle')}<span>${step}</span></div>`).join('')}<div class="mini-heading row between">本次使用的上下文<button class="text-button" data-action="context">查看</button></div><button class="source-row" data-action="context">${icon('layers')}职业背景 · 已确认 v3</button><button class="source-row" data-action="context">${icon('file')}Atlas 项目记录</button><button class="source-row" data-action="job">${icon('globe')}星野 · Agent 研发岗位</button><div class="side-note">${kind === 'execution' ? '申请只在明确授权后提交；结果不确定时先核实，不自动重试。' : '来源不足的内容不会写成已确认事实。材料修改与对外操作分别授权。'}</div>${composer(configuration.prompt,configuration.context,true)}</aside>`;
}

function opportunitiesPage() {
  const candidates = [
    {mark:'星',name:'星野智能',role:'Agent 研发工程师',status:'值得优先看',tag:'live',details:'上海 · 2027 校招 · 工具调用 / 任务执行',reason:'与你的 Agent 工作流经历直接相关；岗位同时强调系统设计与执行可靠性。',unknown:'待确认：团队的交付与研发职责占比。',action:'review',label:'准备这份申请'},
    {mark:'序',name:'序川科技',role:'模型推理工程师',status:'补充信息后判断',tag:'attention',details:'杭州 · 2027 校招 · 推理 / 服务部署',reason:'方向与长期目标相关；需要进一步核对岗位对 C++ 工程经验的要求。',unknown:'待确认：岗位是否接受 Python 服务与模型部署经验。',action:'job',label:'查看岗位依据'},
    {mark:'远',name:'远山实验室',role:'AI 系统研发实习生',status:'实习平行机会',tag:'',details:'上海 · 日常实习 · 系统评测 / Agent',reason:'能积累系统评测的实际证据，可作为正职求职之外的平行选择。',unknown:'待确认：实习时长与课业安排是否兼容。',action:'constraints',label:'对照我的约束'},
  ];
  return `<div class="opportunity-page"><header class="research-summary"><div class="eyebrow">调研成果 / 2027 秋招</div><div class="row between"><h1>这周值得继续了解的机会</h1><span class="tag">一次性调研</span></div><p>先看你进去之后能做什么。以下候选对照了职业目标、现有证据与校招通道；信息不足的地方单独列出。</p><div class="row research-context"><button class="context-chip" data-action="constraints">${icon('target')}Agent / 推理系统</button><span class="context-chip">上海 · 杭州</span><span class="context-chip">官网与指定来源</span><span class="spacer"></span><small class="muted">示例研究 · 09 月 30 日</small></div></header>
    ${candidates.map(candidate=>`<article class="opportunity"><div class="company-mark">${candidate.mark}</div><div><div class="row"><h2>${candidate.name} · ${candidate.role}</h2></div><small>${candidate.details}</small><p>${candidate.reason}</p><small>${candidate.unknown}</small><button class="source-link" data-action="source">官网岗位页 ↗　·　来源与核验说明</button></div><div class="actions"><span class="tag ${candidate.tag}">${candidate.status}</span><button class="button ${candidate.action==='review'?'primary':''}" ${candidate.action==='review'?'data-route':'data-action'}="${candidate.action}">${candidate.label}${candidate.action==='review'?icon('arrow'):''}</button></div></article>`).join('')}
    <div class="research-bottom row between"><small class="muted">推荐依据可追溯，不把“匹配度分数”当作录用概率。</small><button class="text-button" data-action="automations">设置后续关注</button></div>
    ${composer('继续缩小范围，或给我一个想了解的公司…','本次调研 · 职业目标')}
  </div>`;
}

function executionPage() {
  const uncertain = state.execution === 'uncertain';
  const completed = state.execution === 'completed';
  const cancelled = state.execution === 'cancelled';
  return `<div class="task-layout"><section class="task-main"><div class="execution-page"><div class="eyebrow">申请执行 / 星野智能</div><div class="row between"><h1>${completed?'申请已完成，结果已归档':uncertain?'提交结果还不能确定':cancelled?'这次申请已取消':'申请已准备好，提交由你决定'}</h1></div><p>Agent 研发工程师 · 上海 · 校招　/　材料版本 v4</p>
    ${completed?`<section class="result-report"><div class="result-icon">${icon('check')}</div><h2>已读取申请回执</h2><p>本地原型模拟了提交后的读取与记录。真实产品必须从招聘网站取得以下证据，才能显示这个状态。</p><div class="submission-row"><span>申请编号</span><strong>示例回执 · XY-2027-0418</strong></div><div class="submission-row"><span>使用材料</span><strong>Agent 工程方向 · 锁定 v4</strong></div><div class="submission-row"><span>关联结果</span><strong>当次申请预览与回执记录</strong></div><div class="row" style="margin-top:23px"><button class="button primary" data-route="practice">根据这次申请准备面试${icon('arrow')}</button></div></section>`:`${uncertain?'<div class="callout error">提交后未取得可靠回执。保留本次尝试与材料版本，暂停自动提交；先核对官网记录。<button class="text-button" data-action="reconcile">查看对账说明</button></div>':cancelled?'<div class="callout">演示任务已取消，没有提交申请。已审阅的材料仍可继续使用。</div>':'<div class="callout">等待你的确认 · 已核对当次申请预览，尚未提交。</div>'}<div class="browser-frame"><div class="browser-chrome"><span></span><span></span><span></span><div class="browser-address row" style="justify-content:center">${icon('lock')}careers.xingye.example / application / preview</div><small>模拟页面</small></div><div class="website-preview"><div class="website-brand">XINGYE　<span class="muted" style="font-weight:400">星野智能 · 校园招聘</span></div><h2>Agent 研发工程师</h2><small>2027 届校园招聘 / 上海 / 研发</small><div class="submission-preview"><div class="submission-row"><span>申请人</span><strong>林予</strong></div><div class="submission-row"><span>教育背景</span><strong>南川大学 · 人工智能硕士</strong></div><div class="submission-row"><span>附件简历</span><strong>林予_Agent工程_星野_v4.pdf</strong></div><div class="submission-row"><span>当前申请状态</span><strong>${uncertain?'提交结果待核实':'已暂存 · 尚未提交'}</strong></div></div></div><div class="browser-footer"><span>${icon(state.humanControl?'pause':'lock')} ${state.humanControl?'你正在接管 · Agent 已暂停':uncertain?'已停止自动动作 · 等待核实提交结果':cancelled?'已取消 · 未提交':'Agent 已停在提交前'}</span><button class="button" data-action="takeover" ${cancelled?'disabled':''}>${state.humanControl?'交还给 Agent':'接管浏览器'}</button></div></div><div class="execution-facts"><section><h3>本次授权范围</h3><p>星野智能 · 当前岗位 · 材料 v4<br>仅这一次申请，不开启自动投递。</p></section><section><h3>提交后验收</h3><p>重新读取回执与岗位状态<br>不确定时保留证据，交给你核实。</p></section></div><div class="row" style="margin-top:27px"><button class="button primary" data-action="submit-confirm" ${uncertain||cancelled||state.humanControl?'disabled':''}>确认这一次申请${icon('arrow')}</button><button class="button quiet" data-action="cancel" ${completed||cancelled?'disabled':''}>${uncertain?'停止后续动作':'取消任务'}</button></div>`}
    </div></section>${agentPanel('execution')}</div>`;
}

function practicePage() {
  return `<div class="task-layout"><section class="task-main"><div class="document-toolbar row">${icon('book')}项目讲述与面试准备<span class="spacer"></span><span class="tag">可继续编辑的成果</span></div><article class="document"><div class="eyebrow">准备与训练 / 星野 · Agent 研发</div><h1>把你真正做过的事讲清楚</h1><p class="doc-subtitle">结合申请材料与项目证据 · 不背一份泛化题库</p><section class="doc-section"><h2>这次重点准备什么</h2><p>讲清 Agent 从“给出答案”到“完成一项工作”的距离：工具执行、状态保存、失败恢复，以及如何证明结果正确。</p></section><div class="practice-list"><section class="practice-item"><span>01</span><div><h2>用两分钟讲清项目</h2><p>用户遇到了什么重复工作 → 为什么用 Agent → 哪些部分由确定性逻辑兜底 → 最终留下什么可复用的结果。</p><button class="text-button" data-action="practice">打开讲述练习 ↗</button></div></section><section class="practice-item"><span>02</span><div><h2>如果工具超时，为什么不能直接重试？</h2><p>区分读取失败和外部写入结果未知。用一次真实系统设计解释：幂等、状态核验，以及需要人接手的边界。</p><button class="text-button" data-action="add-task">${state.taskAdded?'已加入项目准备任务':'加入我的准备任务'} ↗</button></div></section><section class="practice-item"><span>03</span><div><h2>如何权衡模型效果、延迟与成本？</h2><p>先说明评测样本与基线，再解释模型和工具选择。没有测量的数据要明确说尚未测量。</p><button class="text-button" data-action="evidence">关联一份实验记录 ↗</button></div></section></div><section class="doc-section"><h2>练习后，把新证据带回项目</h2><p class="muted">反馈可以变成准备任务；新的项目实验经确认后补充职业背景，供下一次申请继续使用。</p></section></article></section>${agentPanel('practice')}</div>`;
}

function backgroundPage() {
  const text = state.profileDraft || '希望围绕 Agent、推理与系统持续积累能力。关注岗位实际工作、可迁移的经验，以及团队能否让自己深入解决问题。';
  return `<div class="task-layout"><section class="task-main"><div class="document-toolbar row">${icon('layers')}职业背景<span class="spacer"></span><button class="button quiet" data-action="edit-profile">${icon(state.editing?'check':'edit')}${state.editing?'保存本地草稿':'直接编辑'}</button></div><article class="document"><div class="eyebrow">跨项目背景 · 不等同于某一份对外简历</div><h1>我的职业背景</h1><p class="doc-subtitle">持续积累经历、目标与证据，不需要每次从头解释。</p><section class="doc-section"><div class="row between"><h2>我想往哪里走</h2><span class="tag">${state.profileDraft?'本地草稿 · 待确认':'已确认 · 示例'}</span></div><p id="profile-text" ${state.editing?'contenteditable="true" role="textbox" aria-label="编辑职业目标"':''}>${escapeText(text)}</p></section><hr class="rule"><section class="doc-section"><h2>已经做过的事</h2><p><strong>Atlas · 资料研究 Agent</strong></p><p>实现资料研究工作流、来源关联与成果审阅。任务结果以可编辑内容留存，支持继续修改。</p><button class="source-link" data-action="evidence">查看原始记录与确认依据 ↗</button></section><section class="doc-section"><h2>能力与证据</h2><p>Agent 服务开发 · 模型推理与部署 · 系统评测</p><p class="muted">证据来自项目记录与实验材料；对外材料可以调整表达，不改变已确认事实。</p></section><section class="doc-section"><h2>由这份背景产生的材料</h2><button class="work-row" data-route="review">${icon('file')}<span><strong>简历 · Agent 工程方向</strong><small>用于星野申请 · 有独立的表达与版本</small></span>${icon('arrow')}</button></section></article></section>${agentPanel('background')}</div>`;
}

function portfolioPage() {
  return `<div class="project-page"><div class="eyebrow">职业项目 / 能力积累</div><h1>Agent 工程作品</h1><p class="muted" style="margin-top:10px">把值得展示的能力，做成有真实证据的作品。</p><div class="project-tabs row"><button class="selected">正在推进</button><button data-action="milestones">阶段计划</button></div><div class="brief"><div class="agent-mark">${icon('raven')}</div><div><h2>下一步：补齐一条可复现的执行路径。</h2><p>先让用户真正完成一件事，再用录屏、评测与复现说明展示工程判断。项目成果经确认后，可以关联到秋招材料。</p></div></div><section class="focus-task"><div class="focus-content"><span class="tag live">准备中</span><h2 class="task-title">验证 Agent 的任务恢复与结果核验</h2><p>交付一条可运行路径、一组失败样本，以及说明能力边界的复现记录。</p><div class="progress-line"><span></span></div><div class="row"><span class="context-chip">实现与验证</span><span class="context-chip">失败案例</span><span class="context-chip">演示材料</span></div></div><div class="focus-footer row between"><span>成果可关联职业背景，经确认后再用于申请</span><button class="button" data-action="portfolio-task">继续这项工作${icon('arrow')}</button></div></section>${composer('帮我梳理下一项最值得验证的工程能力…','Agent 工程作品 · 当前目标')}</div>`;
}

function emptyPage() {
  return `<section class="empty"><div class="agent-mark">${icon('raven')}</div><h1>从你正在考虑的下一步开始。</h1><p>可以贴一份已有材料，说说你的目标，或直接从一个岗位开始。背景会在做事的过程中逐步建立。</p>${composer('例如：我明年毕业，想找 Agent 研发方向的工作…','尚未添加项目资料')}<div class="row"><button class="button" data-action="paste">粘贴已有材料</button><button class="button quiet" data-action="recover">看看已有内容的项目${icon('arrow')}</button></div></section>`;
}

function render() {
  const pages = {project:projectPage,review:reviewPage,opportunities:opportunitiesPage,execution:executionPage,practice:practicePage,background:backgroundPage,portfolio:portfolioPage,...workspacePages};
  document.getElementById('app').innerHTML = `<div class="shell">${sidebar()}<main class="workspace">${topbar()}<div class="surface">${workspaceTools()}${pages[state.route]()}</div></main></div>`;
  document.title = `CareerAct · ${state.route === 'project' ? '2027 秋招' : '工作台设计预览'}`;
}

function navigate(route) {
  if (!routes.has(route)) return;
  document.getElementById('context-dialog').close();
  state.route = route;
  state.draft = '';
  state.panelOpen = false;
  location.hash = route;
  render();
}

function toast(message) {
  clearTimeout(toastTimer);
  const element = document.getElementById('toast');
  element.textContent = message;
  element.classList.add('visible');
  toastTimer = setTimeout(()=>element.classList.remove('visible'),4000);
}

function showDialog(title, body, action = '') {
  const dialog = document.getElementById('context-dialog');
  dialog.innerHTML = `<div class="row between"><h2 id="context-title">${title}</h2><button class="icon-button" data-action="close-dialog" aria-label="关闭说明">${icon('close')}</button></div>${body}${action}`;
  dialog.showModal();
}

function decideChange(index, decision) {
  if (state.scenario !== 'normal') { toast('当前模拟了保存或版本问题，请先处理上方提示。'); return; }
  state.changes[index] = decision;
  render();
}

document.addEventListener('input', (event) => {
  const inputKey = event.target.dataset.workInput;
  if (inputKey) {
    workspaceState[inputKey] = event.target.value;
    if (inputKey === 'applicationQuery') document.getElementById('application-results').innerHTML = applicationRows();
    if (inputKey === 'searchQuery') document.getElementById('workspace-search-results').innerHTML = searchWorkspaceRows();
    return;
  }
  if (event.target.matches('[data-composer] textarea')) state.draft = event.target.value;
  if (event.target.id === 'profile-text') state.profileDraft = event.target.textContent;
});

document.addEventListener('submit', (event) => {
  if (handleWorkspaceForm(event)) return;
  if (!event.target.matches('[data-composer]')) return;
  event.preventDefault();
  if (!state.draft.trim()) { event.target.querySelector('textarea').focus(); return; }
  previewDelegation(state.draft);
});

document.addEventListener('change', (event) => {
  const selectKey = event.target.dataset.workSelect;
  if (selectKey) { workspaceState[selectKey] = event.target.value; render(); return; }
  if (!event.target.matches('.preview-select')) return;
  state.scenario = event.target.value;
  if (state.scenario === 'empty') navigate('project');
  else if (state.scenario === 'uncertain') { state.execution = 'uncertain'; navigate('execution'); }
  else if (['save-error','conflict'].includes(state.scenario)) navigate('review');
  else { state.execution = 'ready'; render(); }
});

document.addEventListener('click', async (event) => {
  const target = event.target.closest('button');
  if (!target) return;
  if (target.dataset.workAction) { handleWorkspaceAction(target.dataset.workAction, target); return; }
  if (target.dataset.route) { navigate(target.dataset.route); return; }
  const action = target.dataset.action;
  const actionRoutes = {applications:'applications',library:'library','project-library':'library',automations:'automations',settings:'settings',milestones:'plan',practice:'interviews','portfolio-task':'plan'};
  if (actionRoutes[action]) { navigate(actionRoutes[action]); return; }
  if (action === 'search') { openWorkspaceSearch(); return; }
  if (action === 'paste') { handleWorkspaceAction('intake', target); return; }
  const index = Number(target.dataset.index || 0);
  if (action === 'menu') document.querySelector('.sidebar').classList.toggle('open');
  else if (action === 'panel') { state.panelOpen = !state.panelOpen; document.querySelector('.task-panel')?.classList.toggle('open',state.panelOpen); }
  else if (action === 'mode-read' || action === 'mode-review') { state.mode = action === 'mode-read' ? 'read' : 'review'; render(); }
  else if (action === 'accept-change') decideChange(index,'accepted');
  else if (action === 'reject-change') decideChange(index,'rejected');
  else if (action === 'undo-change') { decideChange(index,'pending'); state.execution = 'ready'; }
  else if (action === 'accept-all') { if (state.scenario !== 'normal') toast('请先处理保存或版本问题。'); else { state.changes = ['accepted','accepted']; render(); toast('已生成示例材料 v4；没有对外提交。'); } }
  else if (action === 'prepare-execution') { if (resolved() && state.scenario === 'normal') navigate('execution'); }
  else if (action === 'recover') { state.scenario = 'normal'; state.execution = 'ready'; render(); toast('已恢复正常演示状态。'); }
  else if (action === 'takeover') { document.getElementById('context-dialog').close(); state.humanControl = !state.humanControl; render(); toast(state.humanControl?'模拟人工接管：Agent 暂停，当前页面没有真实外部会话。':'模拟交还控制：仍等待这一次申请的授权。'); }
  else if (action === 'submit-confirm') showDialog('只授权这一次申请', '<p>星野智能 · Agent 研发工程师 · 材料 v4</p><ul><li>只提交当前岗位，不扩展到其他公司。</li><li>提交后读取结果；未知结果不自动重试。</li><li>本页是原型，点击只模拟成功回执，不访问招聘网站。</li></ul>', '<button class="button primary" data-action="simulate-submit">模拟授权并读取回执</button>');
  else if (action === 'simulate-submit') {
    document.getElementById('context-dialog').close(); state.execution = 'completed';
    const application = workspaceState.applications.find(item => item.id === 'xy-18');
    application.stage = '已投递'; application.raw = '已读取样例申请回执';
    application.source = '模拟回执 · XY-2027-0418'; application.next = '等待筛选并准备面试';
    application.history.push(['本次','已投递','模拟回执 XY-2027-0418 · Agent 方向 v4']);
    const task = workspaceState.tasks.find(item => item.id === 'application');
    task.status = 'completed'; task.result = '已读取模拟回执并关联申请记录'; render();
  }
  else if (action === 'cancel') {
    if (state.execution === 'uncertain') { toast('后续自动动作已停止，已有提交结果仍待核实，不能标记为未提交。'); return; }
    state.execution = 'cancelled'; state.humanControl = false; render();
  }
  else if (action === 'close-dialog') document.getElementById('context-dialog').close();
  else if (action === 'demo-task') { document.getElementById('context-dialog').close(); navigate('review'); }
  else if (action === 'new') { navigate('assistant'); }
  else if (action === 'add-task') { state.taskAdded = true; render(); toast('已加入本地示例项目，可回到“2027 秋招”查看。'); }
  else if (action === 'edit-profile') { state.editing = !state.editing; render(); if (state.editing) document.getElementById('profile-text').focus(); else toast('本地草稿已保留；原型未连接数据库，也未确认新事实。'); }
  else if (action === 'copy') {
    const text = `林予\n人工智能硕士 · 2027 届\n\n项目经历\nAtlas · 资料研究 Agent\n${state.changes[0]==='rejected'?proposals[0].old:proposals[0].next}\n\n技术能力\n${state.changes[1]==='rejected'?proposals[1].old:proposals[1].next}`;
    try { await navigator.clipboard.writeText(text); toast('已复制纯文本，不包含 Markdown 标记。'); }
    catch { showDialog('纯文本内容',`<textarea aria-label="可复制的纯文本" rows="12" style="width:100%;margin-top:16px">${escapeText(text)}</textarea>`); }
  }
  else if (action === 'context' || action === 'project-context') showWorkspaceContext();
  else if (action === 'evidence') showDialog('修改依据', `<p>${proposals[index].reason}</p><ul><li>原始记录：工具调用、任务恢复与结果核验。</li><li>允许：调整表达与内容顺序。</li><li>不允许：虚构用户数、性能数字、工作年限。</li></ul><p>这些均为虚构示例，用来评审来源如何呈现。</p>`);
  else if (action === 'constraints') showDialog('当前项目的选择边界', '<ul><li>方向：Agent、模型推理与系统</li><li>城市：上海、杭州</li><li>机会：校招正职与有帮助的实习分开记录</li><li>判断依据：实际工作、成长空间与证据匹配</li></ul><p>示例约束，不代表项目所有者的私人投递设置。</p>');
  else if (action === 'job' || action === 'source') showDialog('岗位来源与未知信息', '<p>星野智能、序川科技与远山实验室均为虚构公司。本原型没有查询真实招聘信息。</p><ul><li>正式结果应记录原始岗位 URL 与核验时间。</li><li>招聘通道、届次、岗位编号分别核对。</li><li>缺失的截止时间或职责不应由模型补全。</li></ul>');
  else if (action === 'reconcile') showDialog('先核实结果，再决定下一步', '<p>正式产品应读取该岗位的申请记录，保留本次尝试、材料版本和最后观察到的证据。核实前禁止重新提交。</p><p>这里仅展示未知状态；没有发生真实申请或自动重试。</p>');
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') { document.querySelector('.sidebar')?.classList.remove('open'); state.panelOpen = false; document.querySelector('.task-panel')?.classList.remove('open'); }
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); openWorkspaceSearch(); }
});
window.addEventListener('hashchange',()=>{
  const route = location.hash.slice(1);
  if (routes.has(route) && route !== state.route) { state.route=route; state.panelOpen=false; render(); }
});
render();
