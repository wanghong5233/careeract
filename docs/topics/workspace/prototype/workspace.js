const workspaceState = {
  applicationQuery: '', applicationStage: '全部', selectedApplication: 'xc-21', preparationApplication: 'xc-21',
  libraryTab: '全部', preparationTab: '计划', activeMessage: 'hr', searchQuery: '',
  projectMilestone: false, decision: '', factConfirmed: false, growthSaved: false, growthDraft: '',
  intake: '', intakeReviewed: false, materialDraft: '', materialVersion: 4,
  materialHistory: [], practiceAnswer: '', practiceReviewed: false,
  mockMode: '中文文字', mockStarted: false, mockFinished: false,
  automationStatus: '未开启', automationActions: [], automationChannels: ['企业官网'],
  automationFrequency: '每天 09:00', automationExpiry: '2026-10-07',
  automationLimit: 3, automationScope: 'Agent / 推理系统 · 2027 校招 · 上海 / 杭州',
  automationMaterial: '每次人工审阅后锁定的版本', automationReport: '',
  delegatedTask: '', delegatedRoute: 'applications', delegatedContext: '', conversation: [],
  newProject: '', model: '平台模型', deleted: false,
  applications: [
    {id:'xc-21',company:'序川科技',role:'模型推理工程师',code:'XC-21',city:'杭州',channel:'企业官网',batch:'2027 校招正式批',stage:'面试',raw:'待安排技术一面',material:'推理方向 v2',next:'10 月 3 日 14:00 技术一面',source:'招聘邮件 · 09-30 09:10',history:[['09-22','已投递','官网回执 · XC-AP-21'],['09-27','笔试已完成','用户确认 · 成绩未公布'],['09-30','面试','招聘邮件 · 技术一面邀请']]},
    {id:'xy-18',company:'星野智能',role:'Agent 研发工程师',code:'XY-18',city:'上海',channel:'企业官网',batch:'2027 校招正式批',stage:'待提交',raw:'申请表已暂存',material:'Agent 方向 v4',next:'审阅材料并确认本次提交',source:'申请预览 · 09-30',history:[['09-30','待提交','只完成暂存，不代表已投递']]},
    {id:'ys-06',company:'远山实验室',role:'AI 系统研发实习生',code:'YS-06',city:'上海',channel:'BOSS 直聘',batch:'日常实习',stage:'沟通中',raw:'招聘方询问到岗时间',material:'实习方向 v1',next:'确认课业安排，再答复时间',source:'平台消息 · 09-30',history:[['09-28','沟通中','平台打招呼记录'],['09-30','待用户答复','到岗时间不能由 Agent 推定']]},
    {id:'lc-12',company:'澜川软件',role:'后端研发工程师',code:'LC-12',city:'杭州',channel:'猎聘',batch:'2027 校招正式批',stage:'待核实',raw:'官网筛选中 / 邮件显示本轮结束',material:'后端方向 v3',next:'核对邮件是否对应本岗位',source:'两处来源冲突 · 09-29',history:[['09-20','已投递','平台申请记录'],['09-29','待核实','邮件与官网不同步；保留两条观察']]},
    {id:'xc-22',company:'序川科技',role:'AI 平台工程师',code:'XC-22',city:'杭州',channel:'企业官网',batch:'2027 校招正式批',stage:'笔试',raw:'共用测评已完成，等待结果',material:'Agent 方向 v3',next:'等待本岗位结果，不重复测评',source:'用户确认 · 09-27',history:[['09-23','已投递','官网回执 · XC-AP-22'],['09-27','笔试已完成','与 XC-21 共用测评；并非共同进入面试']]},
  ],
  tasks: [
    {id:'research',title:'整理指定来源的岗位变化',status:'running',result:'正在读取已配置来源',route:'opportunities'},
    {id:'application',title:'星野 · 申请执行',status:'waiting',result:'等待本次提交授权',route:'execution'},
    {id:'parse',title:'解析材料中的表格',status:'failed',result:'部分内容无法识别；原件保留',route:'library'},
    {id:'login',title:'恢复招聘平台登录',status:'timed_out',result:'未发生外部写入；需要重新登录',route:'settings'},
    {id:'unknown',title:'核对一条发送结果未知的消息',status:'waiting',result:'等待人工对账；禁止重发',route:'inbox'},
    {id:'report',title:'本周求职回顾',status:'completed',result:'部分完成 · 3 项待处理、1 个来源未读到',route:'reports'},
  ],
};

const workspaceRouteNames = {
  applications:'申请与进展', application:'申请详情', inbox:'沟通与通知', calendar:'日程与待办',
  preparation:'准备与训练', interviews:'模拟面试', decisions:'职业决策', growth:'经历与成长',
  library:'资料与成果', plan:'目标与阶段计划', tasks:'任务中心', automations:'托管服务',
  reports:'结果报告', settings:'偏好与连接', assistant:'与 CareerAct 一起工作',
};

function workspaceHeader(title, description, actions = '') {
  return `<header class="view-heading"><div class="row between"><h1>${title}</h1>${actions}</div><p class="muted">${description}</p></header>`;
}

function searchWorkspaceRows() {
  const query = workspaceState.searchQuery.toLowerCase().trim();
  const records = [
    ...Object.entries(workspaceRouteNames).map(([route,title])=>({route,title,description:'工作视图'})),
    ...workspaceState.applications.map(application=>({id:application.id,title:`${application.company} ${application.role} ${application.code}`,description:`${application.stage} · ${application.material}`})),
    {route:'review',title:'简历 Agent 工程方向',description:'材料 · 固定修改建议'},
    {route:'growth',title:'Atlas 实习 项目 职责 复盘 证据',description:'职业资产'},
  ];
  const matches = records.filter(record=>`${record.title} ${record.description}`.toLowerCase().includes(query));
  return matches.map(record=>`<button class="record-row" ${record.id ? `data-work-action="open-application" data-id="${record.id}"` : `data-route="${record.route}"`}><span><strong>${escapeText(record.title)}</strong><small>${record.description}</small></span></button>`).join('') || '<p class="empty-inline">没有找到，试试公司、编号或内容名称。</p>';
}

function openWorkspaceSearch() {
  workspaceDialog('查找内容',`<label class="field-label">搜索当前样例工作区<input data-work-input="searchQuery" aria-label="查找工作区内容" value="${escapeText(workspaceState.searchQuery)}" placeholder="公司、岗位编号、材料或能力…"></label><div id="workspace-search-results" aria-live="polite">${searchWorkspaceRows()}</div>`);
  document.querySelector('[data-work-input="searchQuery"]').focus();
}

function workspaceTabs(items, selected, action) {
  return `<div class="project-tabs row">${items.map(item=>`<button class="${item === selected ? 'selected' : ''}" data-work-action="${action}" data-value="${item}">${item}</button>`).join('')}</div>`;
}

function projectViews() {
  return `<nav class="view-links" aria-label="项目工作视图">${[['project','工作'],['plan','计划'],['opportunities','机会'],['applications','申请'],['preparation','准备'],['decisions','决策'],['library','资料']].map(([route,label])=>`<button data-route="${route}" class="${state.route === route ? 'selected' : ''}">${label}</button>`).join('')}</nav>`;
}

function workspaceTools() {
  const actions = {
    background:[['intake','添加已有资料'],['profile-facts','事实与证据'],['confirm-fact','确认新事实']],
    opportunities:[['opportunity-inspect','岗位详情与判断'],['watchlist','关注名单与变化'],['research-plan','检索范围与来源']],
    execution:[['field-check','填写、附件与保存核验'],['execution-intervention','登录、验证与人工介入']],
    review:[['format-preview','格式与导出'],['material-history','其他方向材料的版本示例']],
    portfolio:[['create-project','建立另一职业项目'],['project-review','记录项目复盘']],
  };
  const feedback = state.route === 'background' ? `${workspaceState.factConfirmed ? '<div class="callout">新增已确认事实（样例）：本人实现任务状态处理，参与消费端联调；依据为实验记录 A。不含生产规模指标。</div>' : ''}${workspaceState.intakeReviewed ? `<div class="callout"><strong>新增资料 · 待确认草稿</strong><p>${escapeText(workspaceState.intake)}</p></div>` : ''}` : '';
  return actions[state.route] ? `<nav class="workspace-tools" aria-label="相关工作入口">${actions[state.route].map(([action,title])=>`<button class="text-button" data-work-action="${action}">${title}</button>`).join('')}</nav>${feedback}` : '';
}

function showWorkspaceContext() {
  const application = workspaceState.applications.find(item=>item.id === (state.route === 'preparation' ? workspaceState.preparationApplication : workspaceState.selectedApplication));
  const contexts = {
    application:[`${application.company} · ${application.code}`,application.material,'状态历史、来源观察与下一步'],
    preparation:[`${application.company} · ${application.code}`,application.material,'JD、面经、练习记录与薄弱项'],
    applications:['当前筛选条件',`${filteredApplications().length} 条申请`,'逐条状态来源与材料版本'],
    growth:['Atlas 职责笔记','原始实验记录与责任边界','能力账本与待确认事实'],
    portfolio:['Agent 工程作品','当前目标、实验与失败样本','成果与复盘'],
    background:['职业背景 v3','目标、约束、原始证据','未确认草稿不作为正式事实'],
    library:['资料与成果','原件、草稿、表达版本和实投快照','按当前工作选择资料，未全量发送'],
    assistant:[workspaceState.delegatedContext || '当前阶段目标','已确认事实与历史决定','按委托关联工作对象'],
  };
  workspaceDialog('这项工作使用了什么',`<ul>${(contexts[state.route] || ['2027 秋招 · 阶段目标与约束','已确认职业背景 v3','当前工作关联的岗位、材料与来源']).map(context=>`<li>${escapeText(context)}</li>`).join('')}</ul><p>这是原型的上下文展示；正式资料选择、版本读取与模型调用尚未接入。</p>`);
}

function filteredApplications() {
  const terms = workspaceState.applicationQuery.trim().toLowerCase().split(/\s+/);
  return workspaceState.applications.filter(application => terms.every(term => `${application.company} ${application.role} ${application.code} ${application.city} ${application.channel} ${application.batch} ${application.stage}`.toLowerCase().includes(term)) && (workspaceState.applicationStage === '全部' || application.stage === workspaceState.applicationStage));
}

function applicationRows() {
  const applications = filteredApplications();
  return applications.length ? applications.map(application=>`<button class="record-row" data-work-action="open-application" data-id="${application.id}"><span><strong>${application.company} · ${application.role}</strong><small>${application.code} · ${application.channel} · ${application.batch}</small></span><span><span class="tag ${application.stage === '待核实' ? 'attention' : ''}">${application.stage}</span><small>${application.next}</small></span><span class="record-arrow">${icon('arrow')}</span></button>`).join('') : '<p class="empty-inline">没有符合条件的记录。可以清除筛选，或补录一条申请。</p>';
}

function applicationsPage() {
  return `<div class="collection-page">${workspaceHeader('申请与进展','按公司、职位编号或通道找回一次申请，沿记录继续处理。','<button class="button" data-work-action="record-application">补录申请</button>')}${projectViews()}
    <div class="filter-bar"><input aria-label="搜索申请" data-work-input="applicationQuery" value="${escapeText(workspaceState.applicationQuery)}" placeholder="公司、职位编号、岗位、城市或通道"><select aria-label="筛选申请阶段" data-work-select="applicationStage">${['全部','待提交','已投递','简历筛选','沟通中','笔试','面试','待核实','Offer评估','已结束','已入职'].map(stage=>`<option ${workspaceState.applicationStage === stage ? 'selected' : ''}>${stage}</option>`).join('')}</select><button class="button quiet" data-work-action="application-report">汇总这些申请</button></div>
    <section id="application-results" aria-live="polite">${applicationRows()}</section>
    <div class="section-split"><section><h2>申请之前</h2><button class="resource" data-work-action="quota">额度、志愿顺序与重复申请检查 ↗</button><button class="resource" data-route="opportunities">未投机会与关注名单 ↗</button></section><section><h2>接下来</h2><button class="resource" data-route="calendar">笔试、面试与截止时间 ↗</button><button class="resource" data-route="inbox">核对邮件、平台消息与状态变化 ↗</button></section></div>
    ${composer('例如：序川现在到哪一步了？我当时投的是哪个版本？','当前筛选 · 申请与状态历史')}
  </div>`;
}

function applicationPage() {
  const application = workspaceState.applications.find(item=>item.id === workspaceState.selectedApplication);
  return `<div class="collection-page"><button class="text-button" data-route="applications">← 全部申请</button>${workspaceHeader(`${application.company} · ${application.role}`,`${application.code} · ${application.city} · ${application.batch}`,`<span class="tag">${application.stage}</span>`)}
    <div class="callout"><strong>下一步：${escapeText(application.next)}</strong><p>来源：${application.source}。观察结果与个人判断分别保留。</p></div>
    <div class="section-split"><section><h2>这次申请</h2><dl class="detail-list"><dt>通道</dt><dd>${application.channel}</dd><dt>平台原文</dt><dd>${application.raw}</dd><dt>锁定材料</dt><dd>${application.material} · 历史快照</dd><dt>关联岗位</dt><dd>${application.code} · 当时的 JD 与批次</dd></dl><button class="button" data-work-action="locked-material">查看实投版本</button></section><section><h2>状态时间线</h2><ol class="timeline">${application.history.map(([date,stage,evidence])=>`<li><small>${date}</small><strong>${stage}</strong><p>${evidence}</p></li>`).join('')}</ol></section></div>
    <div class="action-strip"><button class="button" data-work-action="status-observation">补充状态观察</button><button class="button" data-work-action="transfer">记录调岗 / HR 转交</button><button class="button" data-work-action="prepare-application">按关联材料准备</button><button class="button quiet" data-route="inbox">沟通与通知样例</button></div>
    ${composer('帮我总结进度、依据和还需要核实的事…',`${application.code} · ${application.material}`)}
  </div>`;
}

function inboxPage() {
  const messages = {hr:{title:'远山 · 招聘方询问到岗时间',channel:'BOSS 直聘',body:'可以每周到岗几天？最早什么时候开始？',basis:'职业背景没有确认课业安排。时间承诺需要你决定。',reply:'感谢沟通，我会核对课业安排后告知可到岗时间。'},notice:{title:'序川 · 技术一面邀请',channel:'招聘邮件',body:'模型推理岗位技术一面，10 月 3 日 14:00，预计 45 分钟。',basis:'仅明确点名 XC-21，不能把 XC-22 同时改成面试。',reply:'感谢邀请，我会确认时间后回复。'},unknown:{title:'澜川 · 上一次消息发送结果未知',channel:'猎聘',body:'发送后连接中断，尚未取得已发送记录。',basis:'先核对会话记录，禁止重新发送。',reply:''}};
  const message = messages[workspaceState.activeMessage];
  return `<div class="collection-page">${workspaceHeader('沟通与通知','消息、招聘通知和待确认承诺，回到同一条申请。','<button class="button" data-work-action="outreach">准备主动沟通</button>')}
    <div class="inbox-layout"><nav aria-label="招聘会话">${Object.entries(messages).map(([id,item])=>`<button class="message-item ${id === workspaceState.activeMessage ? 'selected' : ''}" data-work-action="message" data-id="${id}"><strong>${item.title}</strong><small>${item.channel} · ${id === 'unknown' ? '结果未知' : '待处理'}</small></button>`).join('')}</nav><article class="message-body"><span class="eyebrow">${message.channel} · 虚构会话</span><h2>${message.title}</h2><blockquote>${message.body}</blockquote><p class="callout">${message.basis}</p>${message.reply ? `<label class="field-label">回复草稿<textarea id="reply-draft" rows="4">${message.reply}</textarea></label><div class="action-strip"><button class="button" data-work-action="reply-review">审阅发送</button><button class="button quiet" data-work-action="send-resume">选择简历 / 简历卡</button>${workspaceState.activeMessage === 'notice' ? '<button class="button" data-work-action="notice-calendar">核对并加入日程</button>' : ''}</div>` : '<button class="button" data-work-action="reconcile-message">记录人工核对结果</button>'}<div class="side-note">常规事实回复可按托管授权处理；技术追问、未知意图和时间承诺交给你。</div></article></div>
    <button class="resource" data-route="automations">消息值班、未读巡检与发送授权 ↗</button>
  </div>`;
}

function calendarPage() {
  return `<div class="collection-page">${workspaceHeader('日程与待办','把通知里的时间、申请的下一步和每天的准备放在一起。','<button class="button" data-work-action="reminder">添加提醒</button>')}
    <p class="muted">显示时区：Asia/Shanghai · 日期为原型样例</p><section class="agenda"><h2>10 月 3 日 · 周六</h2><div class="agenda-item"><time>14:00—14:45</time><div><h3>序川 · 技术一面</h3><p>XC-21 · 邀请时间待本人确认 · 面试准备引用推理方向 v2</p><button class="text-button" data-route="preparation">打开准备资料 ↗</button><button class="text-button" data-route="inbox">查看通知来源 ↗</button></div></div><h2>10 月 5 日前</h2><div class="agenda-item"><time>截止 18:00</time><div><h3>补充作品说明</h3><p>来源：招聘邮件 · 保留原文时区；提醒提前 1 天</p><button class="text-button" data-work-action="complete-todo">${workspaceState.todoDone ? '已完成 · 撤回标记' : '标记已完成'}</button></div></div><h2>每天的准备</h2><div class="agenda-item"><time>30 分钟</time><div><h3>算法闭卷复测 + 项目讲述</h3><p>同一份练习结果回到准备计划，不另抄一份完成记录。</p><button class="text-button" data-route="preparation">继续准备 ↗</button></div></div></section>
    <div class="callout">共用笔试只保留一个日程，可关联多个申请；完成笔试不代表所有岗位进入下一阶段。</div>
  </div>`;
}

function preparationPage() {
  const application = workspaceState.applications.find(item=>item.id === workspaceState.preparationApplication);
  const content = {
    '计划':`<h2>序川 · 技术一面准备</h2><p>依据：实投简历「推理方向 v2」、XC-21 JD、公司研究和历史薄弱项。</p><div class="practice-list">${[['公司与团队','先弄清业务、职责和待核实信息','公司研究'],['实习与项目深挖','把个人责任、机制、证据与边界讲清','经历表达'],['算法与知识复习','闭卷复测、错题与概念速查','刷题记录']].map(([title,body,tab])=>`<button class="work-row" data-work-action="preparation-tab" data-value="${tab}">${icon('book')}<span><strong>${title}</strong><small>${body}</small></span>${icon('arrow')}</button>`).join('')}</div><div class="action-strip"><button class="button" data-route="interviews">模拟面试</button><button class="button quiet" data-route="practice">项目讲述示例</button></div>`,
    '公司研究':'<h2>序川 · 公司与岗位研究</h2><p>先分清公司的产品、岗位负责的链路和团队如何衡量结果。</p><dl class="detail-list"><dt>公开事实</dt><dd>示例 JD 侧重推理服务；来源：岗位快照 · 09-22。</dd><dt>判断</dt><dd>与系统方向相关，仍需核对个人实际责任。</dd><dt>待核实</dt><dd>性能优化与客户交付各占多少？部署规模和协作方式是什么？</dd></dl><button class="button" data-work-action="research-plan">查看调研范围与来源</button>',
    '经历表达':'<h2>一段实习如何讲清楚</h2><p>先保留真实职责与技术原材料，再针对岗位整理表达。</p><ol class="content-list"><li>问题与业务价值：为什么值得做？</li><li>个人责任：本人实现、参与联调和团队能力分别是什么？</li><li>关键困难：如何发现、取舍和验证？</li><li>证据与边界：哪些结论有记录，哪些仍未测量？</li></ol><div class="action-strip"><button class="button" data-route="growth">打开经历与复盘</button><button class="button" data-route="review">形成材料修改提议</button></div>',
    '面经':'<h2>面经与问题索引</h2><p>个人面试记录和外部面经分别标记；当时回答与事后补强分开保存。</p><button class="work-row" data-work-action="interview-note"><span><strong>序川 · 一面复盘（样例）</strong><small>个人回忆 · 状态恢复、系统设计 · 2 个薄弱项</small></span></button><button class="work-row" data-work-action="public-interviews"><span><strong>同岗位族公开面经</strong><small>2 条来源合并为 1 组问题 · 非同团队，不能保证命中</small></span></button><button class="button" data-work-action="capture-note">记录一次面试 / 笔试</button>',
    '刷题记录':`<h2>今天继续什么</h2><p>算法手撕、AI 机考、知识概念和 AI Coding 练习可以各自推进。</p><div class="section-split"><section><h3>拓扑排序 · 闭卷复测</h3><p>上次薄弱点：入度变化与循环检测。保留题目、思路、代码、例子和复测记录。</p><label class="field-label">练习笔记<textarea rows="5" data-work-input="practiceAnswer">${escapeText(workspaceState.practiceAnswer)}</textarea></label><button class="button" data-work-action="practice-feedback">记录反馈与下次复习</button></section><section><h3>能力缺口</h3><p>${workspaceState.practiceReviewed ? '已记录：能解释主流程；循环检测仍需闭卷复测。下次准备任务已更新。' : '尚未复测。完成记录不能替代掌握程度。'}</p><button class="text-button" data-route="plan">查看准备任务 ↗</button></section></div>`,
  };
  return `<div class="collection-page">${workspaceHeader('准备与训练','围绕一个岗位，也积累下一次仍然能用的知识与表达。')}${projectViews()}<div class="context-strip">本次上下文：${application.company} · ${application.code} · ${application.material}${application.stage === '待提交' ? '（待提交材料，并非实投）' : ''}</div>${workspaceTabs(Object.keys(content),workspaceState.preparationTab,'preparation-tab')}<article class="reading-content">${application.id !== 'xc-21' ? '<div class="callout">下方是序川的固定交互样例。本岗位的准备内容尚未生成，不将其他公司的研究作为本岗位结论。</div>' : ''}${content[workspaceState.preparationTab]}</article>${composer('根据关联材料和这场面经，调整我的准备重点…',`${application.code} · ${application.material} · 薄弱项`)}</div>`;
}

function interviewsPage() {
  return `<div class="collection-page">${workspaceHeader('模拟面试','后续能力的交互预留 · 当前没有调用模型、录音或开启麦克风。')}
    <div class="context-strip">序川 · XC-21 / 推理方向 v2 / 公司研究 / 个人与公开面经</div>${workspaceTabs(['中文文字','英文文字','实时语音'],workspaceState.mockMode,'mock-mode')}
    <article class="reading-content"><h2>${workspaceState.mockFinished ? '反馈与下一次准备' : '一次有上下文的练习'}</h2>${workspaceState.mockFinished ? '<p>样例反馈：已经解释个人职责；还需要补充失败场景、验证方法及取舍。反馈是练习建议，不是能力认证。</p><button class="button" data-work-action="add-weakness">把薄弱项加入准备计划</button>' : workspaceState.mockStarted ? `<blockquote>${workspaceState.mockMode === '英文文字' ? 'How would you verify the outcome when a tool call times out?' : '工具调用超时后，你如何判断操作是否已经发生？'}</blockquote><textarea aria-label="模拟面试回答" rows="5" placeholder="用你的项目经历回答…"></textarea><div class="action-strip"><button class="button" data-work-action="mock-followup">继续追问</button><button class="button" data-work-action="mock-finish">结束并看反馈</button></div>` : `<p>文字问答支持连续追问；语音模式预留转写、打断、暂停和结束后的反馈。</p><button class="button" data-work-action="mock-start">${workspaceState.mockMode === '实时语音' ? '预览语音会话控件' : '开始样例练习'}</button>`}</article>
  </div>`;
}

function decisionsPage() {
  return `<div class="collection-page">${workspaceHeader('职业决策','投或不投、实习取舍、Offer、入职与离职，都保留当时的依据。')}${projectViews()}
    <article class="reading-content"><h2>Offer 比较 · 样例</h2><p>按自己的目标权衡，不用一个综合分替你决定。</p><div class="table-scroll"><table><thead><tr><th>考虑什么</th><th>序川 · 推理研发</th><th>远山 · 系统实习</th></tr></thead><tbody><tr><th>实际工作</th><td>推理服务与系统优化，待团队核实</td><td>系统评测，已有职责说明</td></tr><tr><th>长期积累</th><td>系统与性能工程</td><td>实验、评估与工程经验</td></tr><tr><th>城市 / 时间</th><td>杭州 · 毕业后入职</td><td>上海 · 需协调课业</td></tr><tr><th>薪酬 / 条件</th><td>尚未收到书面条款</td><td>尚待确认，不推算年包</td></tr><tr><th>决定期限</th><td>未确认</td><td>10 月 7 日前答复（示例）</td></tr></tbody></table></div><label class="field-label">这次选择的理由<textarea rows="3" data-work-input="decision" placeholder="记录当前判断，之后可以复盘…">${escapeText(workspaceState.decision)}</textarea></label><div class="action-strip"><button class="button" data-work-action="save-decision">记录我的决定</button><button class="button quiet" data-route="plan">重新看目标与约束</button></div><p class="muted">保存个人决定不等于向企业接受、拒绝 Offer 或发送离职通知。</p></article>
    <section class="reading-content"><h2>历史选择</h2><p id="decision-history">${workspaceState.decisionSaved ? escapeText(workspaceState.decisionSaved) : '09-28 · 暂缓一项城市不符的机会；依据：阶段目标 v3，日后可以重新评估。'}</p><button class="text-button" data-route="growth">入职后如何继续积累 ↗</button></section>
  </div>`;
}

function growthPage() {
  return `<div class="collection-page">${workspaceHeader('经历与成长','把实习、工作、学习和项目变成可复用的能力证据。','<button class="button" data-work-action="capture-growth">记录一段经历</button>')}
    <article class="reading-content"><div class="eyebrow">Atlas 项目 / 一次故障复盘</div><h2>从超时重试到结果核验</h2><p>问题：重复执行可能产生重复结果。个人负责状态处理与消费端联调，团队提供现有任务设施。</p><h3>行动、取舍与结果</h3><p>把只读重试与外部写入分开，保留每次尝试与核验依据。已有局部实验记录，尚无生产规模指标。</p><details><summary>查看原始证据与责任范围</summary><p>虚构来源：实验记录 A、职责笔记 §2。可定位原件、时间、本人责任及是否仍有效；旧认识不覆盖新确认的事实。</p></details><div class="action-strip"><button class="button" data-work-action="confirm-fact">${workspaceState.factConfirmed ? '已确认样例事实' : '审阅并加入职业背景'}</button><button class="button" data-route="review">提炼为简历表达</button><button class="button quiet" data-work-action="experience-practice">准备项目追问</button></div></article>
    <section class="reading-content"><h2>能力账本</h2><dl class="detail-list"><dt>已有证据</dt><dd>任务状态处理 → 实验记录 A · 本人实现</dd><dt>待补能力</dt><dd>大规模压测 → 尚未做过，不写进正式经历</dd><dt>下一步</dt><dd>完成一次压测实验，再更新判断与准备任务</dd></dl><button class="text-button" data-route="portfolio">继续工程作品项目 ↗</button></section>
    ${workspaceState.growthSaved ? `<div class="callout"><strong>新经历草稿 · 待确认</strong><p>${escapeText(workspaceState.growthDraft)}</p></div>` : ''}
    ${composer('梳理这段实习做了什么、证据在哪里、怎么讲清楚…','职责 · 复盘 · 原始记录')}
  </div>`;
}

function libraryPage() {
  const materials = [
    ['原件','实习职责与项目记录','TXT / DOCX / PDF 来源，保留原件与解析状态','growth'],
    ['材料','简历 · Agent 工程方向','中文基础版 v3 → 待审阅岗位版 v4','review'],
    ['材料','简历 · 推理方向',`草稿 v${workspaceState.materialVersion} · 可阅读、编辑与恢复`,'material'],
    ['材料','英文材料与格式','共用事实，保留语言、字数和版面约束','format'],
    ['锁定版本','序川 · 实际投出的推理方向 v2','只读快照；面试准备引用此版本','locked'],
    ['成果','公司研究、面经与讲述稿','跨项目引用，不重复保存事实副本','preparation'],
  ].filter(([type])=>workspaceState.libraryTab === '全部' || type === workspaceState.libraryTab);
  return `<div class="collection-page">${workspaceHeader('资料与成果','原件、事实、对外表达和任务成果相互关联，在同一处找回。','<button class="button" data-work-action="intake">添加资料</button>')}${workspaceTabs(['全部','原件','材料','锁定版本','成果'],workspaceState.libraryTab,'library-tab')}
    ${materials.map(([type,title,description,route])=>`<button class="record-row" ${route === 'locked' ? 'data-work-action="locked-material"' : route === 'material' ? 'data-work-action="material-reader"' : route === 'format' ? 'data-work-action="format-preview"' : `data-route="${route}"`}><span>${icon('file')} <strong>${title}</strong><small>${description}</small></span><span class="tag">${type}</span></button>`).join('')}
    ${workspaceState.intakeReviewed ? '<div class="callout">粘贴资料已形成待确认草稿。原件和提取出的事实可逐项核对。</div>' : ''}
    <div class="action-strip"><button class="button quiet" data-work-action="material-editor">阅读 / 编辑同一份正文</button><button class="button quiet" data-work-action="material-history">版本与恢复</button><button class="button quiet" data-work-action="format-preview">格式、字数与导出</button></div>
    ${composer('把已有经历整理为一份适合这个岗位的材料…','选定资料 · 已确认背景')}
  </div>`;
}

function planPage() {
  return `<div class="collection-page">${workspaceHeader('目标与阶段计划','目标会变化，保留当时的约束、优先级和复盘。','<button class="button" data-work-action="create-project">建立职业项目</button>')}${projectViews()}
    <article class="reading-content"><div class="eyebrow">2027 秋招 · 目标 v3</div><h2>找到能持续积累 Agent 与系统能力的第一份工作</h2><p>正职与有帮助的实习分别评估；材料叙事不限定真实能力边界。</p><button class="text-button" data-work-action="edit-goal">调整目标、约束与优先级 ↗</button><div class="milestone-list">${[['材料与证据','P0 · 已有基础，继续整理实习证据'],['机会、申请与跟进','P0 · 关注匹配、额度和截止时间'],['面试准备与选择','P1 · 基于实投版本；不等所有申请结束再开始']].map(([title,description],index)=>`<div class="work-row"><span class="tag">${index + 1}</span><span><strong>${title}</strong><small>${description}</small></span></div>`).join('')}</div><div class="action-strip"><button class="button" data-work-action="milestone-done">${workspaceState.projectMilestone ? '已完成证据整理 · 撤销' : '完成证据整理里程碑'}</button><button class="button" data-work-action="project-review">阶段复盘</button><button class="button quiet" data-route="calendar">安排下一步</button></div></article>
    <section class="reading-content"><h2>跨阶段继续使用</h2><p>工程作品、能力提升、入职 90 天与下一次求职，可以各自成为职业项目，共用已确认背景。</p>${workspaceState.newProject ? `<p class="callout">已建立本地项目草稿：${escapeText(workspaceState.newProject)}</p>` : ''}<button class="text-button" data-route="growth">从工作成果回到职业积累 ↗</button></section>
  </div>`;
}

const taskStatusNames = {accepted:'已受理',running:'执行中',waiting:'等待处理',failed:'失败',timed_out:'已超时',cancelled:'已取消',completed:'已完成'};
function tasksPage() {
  return `<div class="collection-page">${workspaceHeader('任务中心','一次工作的进度与结果。长期值班在托管服务中单独管理。','<button class="button" data-route="reports">结果报告</button>')}
    ${workspaceState.tasks.map(task=>`<section class="task-record"><div class="row between"><h2>${escapeText(task.title)}</h2><span class="tag">${taskStatusNames[task.status]}</span></div><p>${escapeText(task.result)}</p><div class="action-strip"><button class="text-button" data-route="${task.route}">打开相关工作 ↗</button>${['running','accepted'].includes(task.status) ? `<button class="text-button" data-work-action="pause-task" data-id="${task.id}">暂停</button>` : ''}${['failed','timed_out'].includes(task.status) || task.paused ? `<button class="text-button" data-work-action="resume-task" data-id="${task.id}">处理后重新执行</button>` : ''}${!['completed','cancelled'].includes(task.status) ? `<button class="text-button" data-work-action="cancel-task" data-id="${task.id}">取消</button>` : ''}</div></section>`).join('')}
    <p class="side-note">原型只模拟状态。正式后台续跑由服务端保存进度；关闭页面后的执行尚未接入。</p>
  </div>`;
}

function automationsPage() {
  return `<div class="collection-page">${workspaceHeader('托管服务','限定来源与授权，让机会巡检、消息值班和信息整理持续进行。',`<span class="tag">${workspaceState.automationStatus}</span>`)}
    <form id="automation-form" class="reading-content"><h2>秋招值班</h2><p>当前仅预览配置，不会创建定时任务或连接招聘平台。</p><fieldset><legend>适用来源</legend>${['企业官网','BOSS 直聘','猎聘','招聘邮件'].map(channel=>`<label class="check-line"><input type="checkbox" name="channel" value="${channel}" ${workspaceState.automationChannels.includes(channel) ? 'checked' : ''}>${channel}</label>`).join('')}</fieldset><label class="field-label">岗位与匹配范围<input name="scope" required value="${escapeText(workspaceState.automationScope)}"></label><label class="field-label">材料版本规则<input name="material" required value="${escapeText(workspaceState.automationMaterial)}"></label><div class="form-grid"><label class="field-label">频率 / 工作时段<select name="frequency">${['每天 09:00','工作日 09:00 / 18:00','每周一 09:00'].map(value=>`<option ${workspaceState.automationFrequency === value ? 'selected' : ''}>${value}</option>`).join('')}</select></label><label class="field-label">有效期至<input name="expiry" type="date" required value="${workspaceState.automationExpiry}"></label><label class="field-label">每日动作上限<input name="limit" type="number" min="1" max="10" value="${workspaceState.automationLimit}" required></label></div><fieldset><legend>允许的动作</legend><p>默认只读巡检、判断与整理。对外动作需要分别选择并审阅范围。</p>${['主动沟通','发送简历','提交申请','常规事实回复'].map(action=>`<label class="check-line"><input name="external" type="checkbox" value="${action}" ${workspaceState.automationActions.includes(action) ? 'checked' : ''}>${action}</label>`).join('')}</fieldset><p class="side-note">未知事实、技术追问与时间承诺转人工；风控停止写入；结果未知不重试。不会覆盖全网。</p><div class="action-strip"><button type="submit" class="button primary">审阅并开启样例服务</button><button type="button" class="button" data-work-action="pause-automation">${workspaceState.automationStatus === '已暂停' ? '恢复值班' : '暂停值班'}</button><button type="button" class="button quiet" data-work-action="revoke-automation">撤销授权</button></div></form>
    <section class="reading-content"><h2>最近一次值班结果</h2><p>${workspaceState.automationReport || '尚未执行。开启服务和执行一次是两件事。'}</p><div class="action-strip"><button class="button" data-work-action="simulate-watch">预览一次巡检结果</button><button class="button quiet" data-route="reports">查看已执行、跳过、失败与待处理</button></div></section>
  </div>`;
}

function reportsPage() {
  return `<div class="collection-page">${workspaceHeader('结果报告','看完成了什么、证据是什么，以及还需要你做什么。')}
    <article class="reading-content"><div class="eyebrow">本周求职回顾 · 样例报告</div><h2>部分完成，仍有三项需要处理</h2><div class="report-item"><span class="tag done">已完成</span><p>整理 3 个候选；来源、核验时间与推荐依据保存在机会中。</p><button class="text-button" data-route="opportunities">打开成果</button></div><div class="report-item"><span class="tag">已跳过</span><p>1 个岗位与既有申请重复，保留职位编号与检查依据。</p><button class="text-button" data-work-action="quota">查看原因</button></div><div class="report-item"><span class="tag attention">失败</span><p>1 个授权来源读取失败；不能解释为“没有新岗位”。</p><button class="text-button" data-route="tasks">处理任务</button></div><div class="report-item"><span class="tag attention">待处理</span><p>到岗承诺、面试时间与一次消息发送结果未知。</p><button class="text-button" data-route="inbox">逐项处理</button></div></article>
    <article class="reading-content"><h2>敏感操作记录</h2><p>一次发送或申请关联岗位、锁定材料、授权范围、尝试时间和外部结果证据。</p><details><summary>查看一次样例申请记录</summary><dl class="detail-list"><dt>动作</dt><dd>序川 XC-21 · 提交申请</dd><dt>材料</dt><dd>推理方向 v2 · 只读快照</dd><dt>授权</dt><dd>用户授权本岗位本次提交，不含后续回复</dd><dt>结果证据</dt><dd>示例回执 XC-AP-21 · 09-22</dd><dt>验收</dt><dd>读取当次岗位申请记录；与编辑态区分</dd></dl></details><button class="text-button" data-route="applications">查找对应申请 ↗</button></article>
  </div>`;
}

function settingsPage() {
  return `<div class="collection-page">${workspaceHeader('偏好与连接','产品账户、模型与授权信息源。这里不授予框架运维权限。')}
    <section class="reading-content"><h2>模型与用量</h2><label class="field-label">模型来源<select data-work-select="model">${['平台模型','阿里云百炼 · BYOK','OpenAI · BYOK'].map(model=>`<option ${workspaceState.model === model ? 'selected' : ''}>${model}</option>`).join('')}</select></label><p>当前选择：${workspaceState.model} · 统一沿用职业上下文。</p><p>预算、调用用量、模型可用性与凭据轮换在此管理。原型不接收真实密钥。</p><button class="button" data-work-action="model-settings">预览用量与密钥管理</button></section>
    <section class="reading-content"><h2>招聘平台与授权来源</h2>${['BOSS 直聘','猎聘','企业官网','招聘邮件'].map(channel=>`<div class="connection-row"><span>${channel}</span><span class="tag">未连接</span><button class="text-button" data-work-action="connection" data-value="${channel}">连接方式</button></div>`).join('')}<button class="text-button" data-route="automations">管理动作授权与撤销 ↗</button></section>
    <section class="reading-content"><h2>我的数据</h2><p>导出项目、档案、材料与申请记录；删除原件、登录态、BYOK 或账户数据。</p><div class="action-strip"><button class="button" data-work-action="data-export">查看导出范围</button><button class="button quiet" data-work-action="data-delete">预览删除与保留策略</button></div><p class="side-note">${workspaceState.deleted ? '已模拟删除请求，可重置演示。没有删除任何真实数据。' : '删除涉及关联材料与历史记录，正式功能需说明影响与备份到期清除。'}</p></section>
  </div>`;
}

function assistantPage() {
  return `<div class="collection-page">${workspaceHeader('与 CareerAct 一起工作','讨论方向、查找进展、整理材料或继续准备，使用同一份职业上下文。')}
    <div class="context-strip">当前项目：2027 秋招 · 已确认背景 v3 · 可选择相关资料</div><div class="intent-links">${[['applications','查一次申请的进度'],['review','把实习写清楚'],['preparation','准备下一场面试'],['decisions','讨论职业选择'],['growth','整理工作成果']].map(([route,label])=>`<button class="button" data-work-action="intent" data-value="${route}">${label}</button>`).join('')}</div>
    ${workspaceState.conversation.map(turn=>`<article class="conversation-turn"><small>${turn.role === 'user' ? '你的委托' : 'CareerAct · 原型预览'}</small><p>${escapeText(turn.text)}</p>${turn.route ? `<button class="button" data-route="${turn.route}">打开相关工作${icon('arrow')}</button>` : ''}</article>`).join('')}
    ${composer('告诉我你现在需要解决的职业问题…','阶段目标 · 相关资料 · 历史决定')}
  </div>`;
}

const workspacePages = {applications:applicationsPage,application:applicationPage,inbox:inboxPage,calendar:calendarPage,preparation:preparationPage,interviews:interviewsPage,decisions:decisionsPage,growth:growthPage,library:libraryPage,plan:planPage,tasks:tasksPage,automations:automationsPage,reports:reportsPage,settings:settingsPage,assistant:assistantPage};

function workspaceDialog(title, body, action = '', label = '保存本地示例') {
  showDialog(title,body,action ? `<div class="action-strip"><button class="button primary" data-work-action="${action}">${label}</button></div>` : '');
}

function previewDelegation(text) {
  workspaceState.delegatedTask = text;
  workspaceState.delegatedContext = state.route === 'portfolio' ? 'Agent 工程作品 · 当前目标与实验记录' : state.route === 'application' ? `${workspaceState.selectedApplication} · 申请、实投材料与状态历史` : `${workspaceRouteNames[state.route] || '2027 秋招'} · 已确认背景与相关资料`;
  workspaceDialog('选择这项工作的去向',`<p>${escapeText(text)}</p><p>原型不推断意图，也不调用模型。选择去向后保留委托与上下文。</p><label class="field-label">工作类型<select id="intent-route">${[['applications','查询申请与进度'],['review','修改材料'],['opportunities','研究机会'],['preparation','准备训练'],['decisions','职业决策'],['growth','整理经历'],['plan','规划项目']].map(([route,label])=>`<option value="${route}" ${workspaceState.delegatedRoute === route ? 'selected' : ''}>${label}</option>`).join('')}</select></label>`,'save-delegation','开始样例工作');
}

function handleWorkspaceAction(action, target) {
  const close = () => document.getElementById('context-dialog').close();
  const value = target.dataset.value;
  const selected = () => workspaceState.applications.find(item=>item.id === workspaceState.selectedApplication);
  if (action === 'open-application') { workspaceState.selectedApplication = target.dataset.id; navigate('application'); }
  else if (action === 'library-tab') { workspaceState.libraryTab = value; render(); }
  else if (action === 'preparation-tab') { workspaceState.preparationTab = value; render(); }
  else if (action === 'message') { workspaceState.activeMessage = target.dataset.id; render(); }
  else if (action === 'intent') { workspaceState.delegatedRoute = value; previewDelegation(target.textContent); }
  else if (action === 'save-delegation') {
    const route = document.getElementById('intent-route').value;
    workspaceState.delegatedRoute = route;
    workspaceState.conversation.push({role:'user',text:`${workspaceState.delegatedTask}\n上下文：${workspaceState.delegatedContext}`},{role:'assistant',text:'已保留这次委托。下面打开相关工作与已有记录；正式 Agent 的分析与执行尚未接入。',route});
    workspaceState.tasks.push({id:`local-${workspaceState.tasks.length}`,title:workspaceState.delegatedTask,status:'accepted',result:'本地委托已受理，等待接入真实执行',route}); close(); navigate('assistant');
  }
  else if (action === 'application-report') {
    const applications = filteredApplications();
    workspaceDialog('当前申请汇总',`<p>共 ${applications.length} 条匹配记录；以下来自本地样例，没有向官网重新查询。</p>${applications.map(application=>`<p><strong>${application.company} · ${application.code}</strong><br>${application.stage}；${application.next}<br>依据：${application.source}；材料：${application.material}</p>`).join('') || '<p>没有符合筛选条件的申请。</p>'}`);
  }
  else if (action === 'quota') workspaceDialog('额度、志愿与重复检查','<p>公司 + 职位编号 + 招聘批次 + 通道共同核对。额度按企业规则分组，不把每家公司简化为一个数字。</p><ul><li>序川正式批：2 个志愿已使用；两岗共用测评，但状态分别跟进。</li><li>远山实习：与正职分开记录，不自动占用正职额度。</li><li>同岗位跨渠道、转交或补投先核实，不能仅按标题判重。</li><li>规则保留来源、核验时间和未知项；有冲突先暂停申请。</li></ul>');
  else if (action === 'record-application') workspaceDialog('补录既有申请','<p>粘贴回执或口述记录 → 提取岗位、通道与时间 → 检查重复 → 由你核对后记账。补录不会向企业提交申请。</p><label class="field-label">申请记录<textarea id="record-text" rows="4" placeholder="公司、岗位编号、批次、投递时间和依据…"></textarea></label>','preview-record','查看待核对记录');
  else if (action === 'preview-record') { const text = document.getElementById('record-text').value.trim(); if (!text) return toast('先填写记录。'); workspaceDialog('待核对记录',`<p>${escapeText(text)}</p><p>岗位身份、材料版本与外部证据待逐项核实。解析与防重接口尚未接入，当前不写入申请总表。</p>`); }
  else if (action === 'locked-material') { const application = state.route === 'library' ? workspaceState.applications.find(item=>item.id === 'xc-21') : selected(); workspaceDialog(application.stage === '待提交' ? '关联材料 · 尚未投出' : '实投材料 · 只读快照',`<p>${application.company} · ${application.material}</p><p>Atlas · 资料研究 Agent：实现资料关联与任务结果核验。${application.stage === '待提交' ? '当前只准备材料，没有提交回执。' : '此处代表当时投出的内容；当前基础简历改写不会覆盖它。'}</p><p>可据此准备面试，或复制成新的草稿。恢复旧版本也要生成新版本。</p>`); }
  else if (action === 'prepare-application') { workspaceState.preparationApplication = workspaceState.selectedApplication; navigate('preparation'); }
  else if (action === 'status-observation') workspaceDialog('补充状态观察','<label class="field-label">状态<select id="observation-stage"><option>简历筛选</option><option>笔试</option><option>面试</option><option>Offer评估</option><option>已结束</option><option>已入职</option><option>待核实</option></select></label><label class="field-label">来源 / 原文 / 时间<textarea id="observation-text" rows="3" placeholder="区分官方通知、用户确认和个人推测…"></textarea></label>','save-observation','追加观察记录');
  else if (action === 'save-observation') { const text = document.getElementById('observation-text').value.trim(); if (!text) return toast('需要保留观察依据，不能只改状态。'); const stage = document.getElementById('observation-stage').value; const application = selected(); application.history.push(['本次',escapeText(stage),escapeText(`用户补充：${text}`)]); application.stage = stage; application.source = '用户补充 · 未自动核验，旧平台观察保留'; application.next = '核对新增观察及下一步'; close(); render(); }
  else if (action === 'transfer') workspaceDialog('调岗与转交','<p>保留原申请和旧岗位身份，为新岗位建立关联记录；区分 HR 转交、重新投递与系统改岗。是否占额度仍需来源证据。</p><label class="field-label">新岗位与依据<textarea rows="3" placeholder="新职位编号、团队、通道、通知来源…"></textarea></label><p class="side-note">此处预留关联确认 UI，尚未接入岗位转移接口。</p>');
  else if (action === 'reply-review') { const reply = document.getElementById('reply-draft').value.trim(); if (!reply) return toast('回复草稿为空。'); workspaceDialog('审阅这一次回复',`<p>${escapeText(reply)}</p><p>仅当前会话，未附加简历。时间承诺需要本人确认；此按钮只模拟发送结果。</p>`,'simulate-reply','模拟确认并发送'); }
  else if (action === 'simulate-reply') { close(); toast('已模拟发送并读取结果；真实消息未发送。'); }
  else if (action === 'outreach' || action === 'send-resume') workspaceDialog(action === 'outreach' ? '主动沟通草稿' : '选择发送材料','<p>收件对象：远山 · YS-06 / BOSS 直聘。先核对历史触达，避免重复联系。</p><label class="field-label">材料<select><option>不附材料，仅打招呼</option><option>实习方向 v1 · PDF</option><option>已确认的平台简历卡</option></select></label><label class="field-label">消息<textarea rows="3">您好，我对这个岗位的系统评测工作感兴趣，希望进一步了解职责范围。</textarea></label><p class="side-note">草稿与材料选择已预留；正式发送需绑定本次授权、版本与读取结果。</p>');
  else if (action === 'reconcile-message') workspaceDialog('核对未知结果','<p>查看原会话的已发送记录，并匹配内容、时间及附件。找到证据后记录结果；没有证据仍保持待核实，不能自动重发。</p><button class="button" data-route="reports">查看操作记录</button>');
  else if (action === 'notice-calendar') { navigate('calendar'); toast('样例日程关联 XC-21；尚未对外确认参加。'); }
  else if (action === 'reminder') workspaceDialog('提醒与日程','<label class="field-label">提醒事项<input value="准备序川技术一面"></label><label class="field-label">时间<input type="datetime-local" value="2026-10-02T14:00"></label><p>Asia/Shanghai · 关联 XC-21 · 通知渠道尚未接入。</p>','save-reminder','保存样例提醒');
  else if (action === 'save-reminder') { close(); toast('已模拟保存提醒；不会发送系统通知。'); }
  else if (action === 'complete-todo') { workspaceState.todoDone = !workspaceState.todoDone; render(); }
  else if (action === 'research-plan') workspaceDialog('公司研究范围','<ul><li>官网、岗位 JD、公开业务资料；标明更新时间。</li><li>公开面经标注来源与岗位相关性，合并重复问题。</li><li>结论区分事实、推断、未知，不承诺信息完整。</li></ul><button class="button" data-route="opportunities">回到机会研究</button>');
  else if (action === 'opportunity-inspect') workspaceDialog('星野 · XY-18 · 岗位判断','<dl class="detail-list"><dt>JD 要点</dt><dd>工具调用、任务执行与系统可靠性；上海，2027 校招；薪资、截止日期未确认。</dd><dt>来源与时效</dt><dd>企业官网岗位页快照 · 示例核验 09-30；可关联 BOSS / 猎聘同岗位线索。</dd><dt>匹配依据</dt><dd>背景 v3 与 Atlas 实验记录支持 Agent 服务经历；团队职责占比未知。</dd><dt>申请检查</dt><dd>已有 XY-18 暂存记录，尚未提交。继续该申请，不新建重复申请。</dd></dl><div class="action-strip"><button class="button" data-route="review">继续已有申请准备</button><button class="button" data-work-action="skip-opportunity">记录暂不考虑的原因</button></div>');
  else if (action === 'skip-opportunity') workspaceDialog('暂不考虑这项机会','<label class="field-label">原因<textarea id="skip-reason" rows="3" placeholder="例如：城市不符；保留原因，避免反复推荐…"></textarea></label>','save-skip','记入关注判断');
  else if (action === 'save-skip') { const reason = document.getElementById('skip-reason').value.trim(); if (!reason) return toast('先补充原因。'); workspaceState.skippedReason = reason; close(); toast('已记录到关注名单；后续需由新证据重新评估。'); }
  else if (action === 'watchlist') workspaceDialog('关注名单与岗位变化',`<div class="report-item"><span class="tag">新开放</span><p>序川 · 指定官网发现模型推理校招；09-30 核验。</p></div><div class="report-item"><span class="tag attention">待核实</span><p>远山 · 招聘线索来自转载，未确认官网通道与届次。</p></div><div class="report-item"><span class="tag">暂缓</span><p>${escapeText(workspaceState.skippedReason || '星野 · 团队职责占比待了解，保留判断与依据。')}</p></div><p>关注名单区别于已投总表；指定来源的新开、改动和关闭由定时任务核对。</p><button class="button" data-route="automations">设置定期关注</button>`);
  else if (action === 'profile-facts') workspaceDialog('职业事实与原始证据','<dl class="detail-list"><dt>教育</dt><dd>南川大学 · 人工智能硕士 · 在读；学籍原件作为来源。</dd><dt>经历 / 项目</dt><dd>Atlas 项目、实习职责；区分本人、参与、团队能力。</dd><dt>成果</dt><dd>论文、证书、荣誉；发表与在审状态分别确认。</dd><dt>技能</dt><dd>已有实践与待补能力分开，关联实验和工作记录。</dd><dt>目标 / 约束</dt><dd>城市、方向、时间、薪资及个人边界，允许版本调整。</dd></dl><p>真实联系方式、证件、地址和证明人仅在必要的受控字段中核对；不进入公开简历正文。</p><button class="button" data-route="growth">打开能力账本</button>');
  else if (action === 'field-check') workspaceDialog('当次岗位申请 · 填写与核验','<p>当前对象：星野 XY-18 的申请表，不能用个人中心简历代替。</p><div class="table-scroll"><table><thead><tr><th>字段 / 材料</th><th>填写依据</th><th>保存后预览</th></tr></thead><tbody><tr><td>教育、日期、列表</td><td>已确认背景 v3；覆盖旧值</td><td>样例：已读回</td></tr><tr><td>城市 / 级联选项</td><td>上海；按当前表单映射</td><td>样例：已读回</td></tr><tr><td>项目正文 / 链接</td><td>锁定材料 v4；长度与链接口径</td><td>样例：已读回</td></tr><tr><td>附件</td><td>当前岗位锁定 PDF v4</td><td>样例：文件名与版本核对</td></tr><tr><td>无法映射的必填项</td><td>需用户补充，不编造</td><td>阻止提交</td></tr></tbody></table></div><p>预留字段修正、附件上传与读回接口；当前不操作真实表单。</p>');
  else if (action === 'execution-intervention') workspaceDialog('暂停执行，处理当前问题','<label class="field-label">介入原因<select><option>登录过期</option><option>验证码 / 平台风控</option><option>必填字段无法映射</option><option>不可逆动作等待授权</option></select></label><p>同一会话先暂停 Agent 再接管。会话已失效时，不承诺恢复未保存页面；结果未知先对账。</p><button class="button" data-action="takeover">预览接管状态</button><button class="button" data-route="tasks">保留进度，稍后处理</button>');
  else if (action === 'interview-note' || action === 'capture-note') workspaceDialog('面试 / 笔试复盘','<label class="field-label">当场问题与回答<textarea rows="4" placeholder="日期、申请、轮次、问题、当时怎么回答…"></textarea></label><label class="field-label">事后补强<textarea rows="3" placeholder="不足、依据、下次怎么讲；不改写当场事实…"></textarea></label><p>关联 XC-21 · 个人记录，与网上面经分开。</p>','save-note','记录并生成准备任务');
  else if (action === 'save-note' || action === 'add-weakness') { state.taskAdded = true; close(); navigate('preparation'); toast('已模拟把薄弱项加入准备任务；未自动确认能力事实。'); }
  else if (action === 'public-interviews') workspaceDialog('公开面经去重与出处','<p>问题组：工具超时与重复执行。</p><ul><li>来源 A：同岗位族，09-20。</li><li>来源 B：转载 A，合并保留出处。</li><li>原问题、岗位 / 轮次、适用性与未知项分别记录。</li></ul><p>样例来源，不是实际检索结果。</p>');
  else if (action === 'practice-feedback') { if (!workspaceState.practiceAnswer.trim()) return toast('先记录练习情况。'); workspaceState.practiceReviewed = true; state.taskAdded = true; render(); }
  else if (action === 'mock-mode') { workspaceState.mockMode = value; workspaceState.mockStarted = false; workspaceState.mockFinished = false; render(); }
  else if (action === 'mock-start') { if (workspaceState.mockMode === '实时语音') workspaceDialog('实时语音会话预留','<p>状态：尚未连接。正式功能包含麦克风授权、转写、打断、静音、暂停 / 恢复和结束后反馈。</p><div class="action-strip"><button class="button" disabled>连接语音</button><button class="button" disabled>静音 / 暂停</button><button class="button" disabled>结束会话</button></div><p>当前没有录音，也不请求麦克风权限。</p>'); else { workspaceState.mockStarted = true; render(); } }
  else if (action === 'mock-followup') workspaceDialog('连续追问 · 样例','<p>如果外部服务没有幂等键，你如何取得可靠结果？请补充你实际做过的验证。</p><textarea aria-label="追问回答" rows="4"></textarea><p>固定样例追问，没有对答案做模型评价。</p>');
  else if (action === 'mock-finish') { workspaceState.mockFinished = true; render(); }
  else if (action === 'save-decision') { if (!workspaceState.decision.trim()) return toast('先写下选择与理由。'); workspaceState.decisionSaved = `${workspaceState.decision}（关联目标 v3；仅记录个人决定）`; render(); }
  else if (action === 'capture-growth') workspaceDialog('记下一段经历','<label class="field-label">发生了什么<textarea id="growth-text" rows="5" placeholder="问题、个人责任、行动与取舍、结果、证据、是否仍有效…"></textarea></label>','save-growth');
  else if (action === 'save-growth') { const text = document.getElementById('growth-text').value.trim(); if (!text) return toast('先补充经历。'); workspaceState.growthDraft = text; workspaceState.growthSaved = true; close(); render(); }
  else if (action === 'confirm-fact') workspaceDialog('确认事实与责任范围','<p>样例事实：本人实现任务状态处理，并参与消费端联调。依据：实验记录 A 与职责笔记 §2；不包含生产规模指标。</p><p>确认后供相关项目复用；不会自动改写已投材料。</p>','save-fact','确认这条样例事实');
  else if (action === 'save-fact') { workspaceState.factConfirmed = true; close(); render(); }
  else if (action === 'experience-practice') { workspaceState.preparationTab = '经历表达'; navigate('preparation'); }
  else if (action === 'intake') workspaceDialog('从已有资料开始','<label class="field-label">粘贴或讲述<textarea id="intake-text" rows="5" placeholder="只使用虚构内容；真实资料请等私有导入链路接入…"></textarea></label><div class="action-strip"><button class="button" disabled>导入 PDF / DOCX / TXT</button><button class="button" disabled>语音讲述</button></div><p>文件选择、解析进度、失败重试、原件保留与事实核对是后续接口入口。</p>','review-intake','预览待确认内容');
  else if (action === 'review-intake') { const text = document.getElementById('intake-text').value.trim(); if (!text) return toast('先粘贴内容。'); workspaceState.intake = text; workspaceState.intakeReviewed = true; workspaceDialog('待确认草稿',`<p>${escapeText(text)}</p><p>来源：本次粘贴。保存草稿不代表事实已确认；解析与字段映射尚未实现。</p><button class="button" data-route="background">去背景中核对</button>`); }
  else if (action === 'material-reader') workspaceDialog(`推理方向 · 草稿 v${workspaceState.materialVersion}`,`<p style="white-space:pre-wrap">${escapeText(workspaceState.materialDraft || 'Atlas · 资料研究 Agent\n本人实现资料研究工作流与结果核验，保留来源，支持继续编辑成果。')}</p><button class="button" data-work-action="material-history">版本与恢复</button>`,'material-editor','直接编辑');
  else if (action === 'material-editor') workspaceDialog('推理方向 · 编辑当前正文',`<label class="field-label">正文<textarea id="material-text" rows="8">${escapeText(workspaceState.materialDraft || 'Atlas · 资料研究 Agent\n本人实现资料研究工作流与结果核验，保留来源，支持继续编辑成果。')}</textarea></label><p>阅读与编辑使用同一份草稿；Agent 提议的 Diff 在另一份 Agent 方向材料中演示。</p>`,'save-material','保存新草稿版本');
  else if (action === 'save-material') { const text = document.getElementById('material-text').value.trim(); if (!text) return toast('正文不能为空。'); workspaceState.materialHistory.push({version:workspaceState.materialVersion,text:workspaceState.materialDraft || 'Atlas · 资料研究 Agent\n本人实现资料研究工作流与结果核验，保留来源，支持继续编辑成果。'}); workspaceState.materialDraft = text; workspaceState.materialVersion += 1; close(); render(); handleWorkspaceAction('material-reader', target); toast(`本地草稿 v${workspaceState.materialVersion}；历史申请快照不变。`); }
  else if (action === 'material-history') workspaceDialog('版本与恢复',`<p>当前草稿 v${workspaceState.materialVersion}，实投版本独立锁定。</p>${workspaceState.materialHistory.length ? workspaceState.materialHistory.map((version,index)=>`<button class="resource" data-work-action="restore-material" data-id="${index}">恢复 v${version.version} 为新草稿</button>`).join('') : '<p>尚无本地编辑历史。先编辑并保存一份草稿。</p>'}`);
  else if (action === 'restore-material') { const previous = workspaceState.materialHistory[Number(target.dataset.id)]; workspaceState.materialHistory.push({version:workspaceState.materialVersion,text:workspaceState.materialDraft}); workspaceState.materialDraft = previous.text; workspaceState.materialVersion += 1; close(); render(); toast('已恢复为新的草稿版本，不覆盖旧版本或实投材料。'); }
  else if (action === 'format-preview') workspaceDialog('格式与导出','<label class="field-label">使用场景<select><option>官网文本栏 · 500 字以内</option><option>中文 PDF · 1 页</option><option>英文 PDF · 1 页</option><option>纯文本 / Markdown</option></select></label><p>正式功能应核对字数、列表、链接、附件与版面；不改事实满足限制。</p><button class="button" disabled>排版预览与文件导出 · 待接入</button><button class="button" data-route="review">打开现有材料与纯文本复制</button>');
  else if (action === 'create-project') workspaceDialog('建立职业项目','<label class="field-label">这一阶段想完成什么<input id="project-name" placeholder="例如：入职后的 90 天"></label><label class="field-label">项目类型<select><option>求职</option><option>能力提升</option><option>工程作品</option><option>转岗</option><option>入职成长</option></select></label>','save-project');
  else if (action === 'save-project') { const title = document.getElementById('project-name').value.trim(); if (!title) return toast('请先写下阶段目标。'); workspaceState.newProject = title; close(); render(); }
  else if (action === 'milestone-done') { workspaceState.projectMilestone = !workspaceState.projectMilestone; render(); }
  else if (action === 'edit-goal') workspaceDialog('阶段目标与选择边界','<label class="field-label">目标、硬约束、优先级<textarea id="goal-text" rows="5" placeholder="城市、方向、时间、薪资与个人边界；区分硬约束和偏好…"></textarea></label><p>变化保留时间与理由；旧申请和决定引用当时版本。</p>','save-goal','记录目标调整草稿');
  else if (action === 'save-goal') { const text = document.getElementById('goal-text').value.trim(); if (!text) return toast('先写下调整内容。'); state.profileDraft = text; close(); navigate('background'); }
  else if (action === 'project-review') workspaceDialog('阶段复盘','<label class="field-label">结果与下一阶段<textarea rows="5" placeholder="哪些行动有效？哪些假设不成立？下阶段目标、时间与任务如何调整？"></textarea></label><p>关联任务结果、材料与决定；项目可归档并被下一阶段引用。归档与恢复接口待接入。</p>');
  else if (['pause-task','resume-task','cancel-task'].includes(action)) { const task = workspaceState.tasks.find(item=>item.id === target.dataset.id); task.status = action === 'pause-task' ? 'waiting' : action === 'cancel-task' ? 'cancelled' : 'accepted'; task.paused = action === 'pause-task'; task.result = action === 'pause-task' ? '用户暂停；保留业务进度' : action === 'cancel-task' ? '停止尚未执行的动作；不撤回已发生的外部动作' : '重新受理安全步骤；真实执行尚未接入'; render(); }
  else if (action === 'confirm-automation') { workspaceState.automationStatus = '已开启（模拟）'; close(); render(); }
  else if (action === 'pause-automation') { if (!['已开启（模拟）','已暂停'].includes(workspaceState.automationStatus)) return toast('先审阅并开启服务。'); workspaceState.automationStatus = workspaceState.automationStatus === '已暂停' ? '已开启（模拟）' : '已暂停'; render(); }
  else if (action === 'revoke-automation') { workspaceState.automationStatus = '已撤销'; workspaceState.automationActions = []; render(); toast('已模拟停止未执行的授权动作；历史记录保留。'); }
  else if (action === 'simulate-watch') { if (workspaceState.automationStatus !== '已开启（模拟）') return toast('服务未开启或已暂停 / 撤销。'); workspaceState.automationReport = '样例：2 条新机会、1 条重复跳过；1 个来源读取失败。验证码触发时停止自动写入并通知，时间承诺转人工。'; render(); }
  else if (action === 'model-settings') workspaceDialog('模型与凭据','<p>模型路由、预算 / 用量、限流、BYOK 添加 / 轮换 / 删除预留在此；始终使用同一职业上下文。</p><input aria-label="BYOK 密钥（原型不接收）" placeholder="密钥输入在原型中禁用" disabled><p>当前没有读取配置或真实用量。平台运维账号不等于产品管理员。</p>');
  else if (action === 'connection') workspaceDialog(`${value} · 连接与撤销`,'<p>招聘平台通过隔离浏览器登录；邮件通过授权连接器。连接登录态不等于授权发送或投递。</p><div class="action-strip"><button class="button" disabled>登录 / 授权连接 · 待接入</button><button class="button" disabled>撤销并删除登录态 · 待接入</button></div><p>过期与风控要重新处理；不采集平台明文密码。</p>');
  else if (action === 'data-export') workspaceDialog('数据导出范围','<ul><li>职业项目、背景及确认状态</li><li>材料正文、版本、原件与引用关系</li><li>申请、沟通、状态历史、决策与报告</li></ul><button class="button" disabled>导出私有数据包 · 待接入</button>');
  else if (action === 'data-delete') workspaceDialog('删除与保留策略','<p>可分别删除文件、平台登录态、BYOK 或账户。账户删除应撤销托管和访问，处理关联数据，说明备份的保留期限。</p><p>当前只模拟请求，不访问真实数据。</p>','simulate-delete','模拟删除请求');
  else if (action === 'simulate-delete') { workspaceState.deleted = true; close(); render(); }
  else return false;
  return true;
}

function handleWorkspaceForm(event) {
  if (event.target.id !== 'automation-form') return false;
  event.preventDefault();
  const values = new FormData(event.target);
  const channels = values.getAll('channel');
  if (!channels.length) { toast('至少选择一个授权来源。'); return true; }
  workspaceState.automationChannels = channels;
  workspaceState.automationActions = values.getAll('external');
  workspaceState.automationFrequency = values.get('frequency');
  workspaceState.automationExpiry = values.get('expiry');
  workspaceState.automationScope = values.get('scope');
  workspaceState.automationMaterial = values.get('material');
  workspaceState.automationLimit = Number(values.get('limit'));
  workspaceDialog('审阅托管范围',`<p>来源：${escapeText(channels.join('、'))}</p><p>范围：${escapeText(workspaceState.automationScope)}</p><p>动作：只读巡检与整理${workspaceState.automationActions.length ? '；'+escapeText(workspaceState.automationActions.join('、')) : '；所有对外动作关闭'}</p><p>材料：${escapeText(workspaceState.automationMaterial)}</p><p>${workspaceState.automationFrequency} · 每日最多 ${workspaceState.automationLimit} 次 · 至 ${workspaceState.automationExpiry}</p><p>仅模拟授权；实际平台、调度、预算与风控校验尚未接入。</p>`,'confirm-automation','确认这份样例授权');
  return true;
}
