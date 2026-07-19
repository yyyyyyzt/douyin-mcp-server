/**
 * 对话场景模型：统一「问答 / 报价单 / 进度 / 记账 / 预算」等交互入口。
 * 后期新增能力时扩展 SCENARIO_KINDS + QUICK_SCENARIOS，并在 chat-message 组件增加渲染分支。
 */

const SCENARIO_KINDS = {
  KNOWLEDGE_QA: 'knowledge_qa',
  QUOTE_REVIEW: 'quote_review',
  PROGRESS_TRACK: 'progress_track',
  EXPENSE_LOG: 'expense_log',
  BUDGET_GUARD: 'budget_guard',
};

const ATTACHMENT_KINDS = {
  DOCUMENT: 'document',
  RECEIPT: 'receipt',
  PROGRESS_SNAPSHOT: 'progress_snapshot',
};

/** 快捷场景：enabled=false 的项在 UI 展示「即将上线」，不发起请求 */
const QUICK_SCENARIOS = [
  {
    id: 'qa_waterproof',
    label: '卫生间防水要注意什么？',
    kind: SCENARIO_KINDS.KNOWLEDGE_QA,
    prompt: '卫生间防水要注意什么？',
    enabled: true,
  },
  {
    id: 'quote_review',
    label: '帮我看报价单有没有漏项',
    kind: SCENARIO_KINDS.QUOTE_REVIEW,
    prompt: '帮我看报价单有没有漏项',
    enabled: true,
    attachmentKind: ATTACHMENT_KINDS.DOCUMENT,
  },
  {
    id: 'qa_acceptance',
    label: '水电验收要检查哪些地方？',
    kind: SCENARIO_KINDS.KNOWLEDGE_QA,
    prompt: '水电验收要检查哪些地方？',
    enabled: true,
  },
  {
    id: 'expense_log',
    label: '记一笔装修花费',
    kind: SCENARIO_KINDS.EXPENSE_LOG,
    prompt: '记一笔今天的装修花费',
    enabled: false,
    badge: '即将上线',
  },
  {
    id: 'budget_guard',
    label: '看看预算还剩多少',
    kind: SCENARIO_KINDS.BUDGET_GUARD,
    prompt: '目前装修预算还剩多少？',
    enabled: false,
    badge: '即将上线',
  },
  {
    id: 'progress_track',
    label: '更新今日施工进度',
    kind: SCENARIO_KINDS.PROGRESS_TRACK,
    prompt: '更新一下今天的施工进度',
    enabled: false,
    badge: '即将上线',
  },
];

const ATTACHMENT_LABELS = {
  [ATTACHMENT_KINDS.DOCUMENT]: '报价单',
  [ATTACHMENT_KINDS.RECEIPT]: '收据',
  [ATTACHMENT_KINDS.PROGRESS_SNAPSHOT]: '进度',
};

function newId(prefix) {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

function createUserMessage({ text, kind, attachment }) {
  return {
    id: newId('u'),
    role: 'user',
    kind: kind || SCENARIO_KINDS.KNOWLEDGE_QA,
    content: (text || '').trim(),
    attachment: attachment || null,
    createdAt: Date.now(),
  };
}

function createAssistantPlaceholder(kind) {
  return {
    id: newId('a'),
    role: 'assistant',
    kind: kind || SCENARIO_KINDS.KNOWLEDGE_QA,
    content: '',
    pending: true,
    grounded: true,
    citations: [],
    meta: {},
  };
}

function attachmentLabel(attachment) {
  if (!attachment) return '';
  const kindLabel = ATTACHMENT_LABELS[attachment.kind] || '附件';
  const name = attachment.filename || attachment.name || '';
  return name ? `${kindLabel}: ${name}` : kindLabel;
}

function formatUserDisplay(message) {
  if (!message) return '';
  if (message.attachment) {
    return `${message.content} [${attachmentLabel(message.attachment)}]`;
  }
  return message.content;
}

function isFutureScenario(kind) {
  return [
    SCENARIO_KINDS.EXPENSE_LOG,
    SCENARIO_KINDS.BUDGET_GUARD,
    SCENARIO_KINDS.PROGRESS_TRACK,
  ].includes(kind);
}

function buildChatRequestBody(message, attachment) {
  const body = { question: message.content };
  if (attachment && attachment.kind === ATTACHMENT_KINDS.DOCUMENT && attachment.text) {
    body.document_text = attachment.text;
    body.document_name = attachment.filename;
  }
  return body;
}

module.exports = {
  SCENARIO_KINDS,
  ATTACHMENT_KINDS,
  QUICK_SCENARIOS,
  ATTACHMENT_LABELS,
  createUserMessage,
  createAssistantPlaceholder,
  attachmentLabel,
  formatUserDisplay,
  isFutureScenario,
  buildChatRequestBody,
};
