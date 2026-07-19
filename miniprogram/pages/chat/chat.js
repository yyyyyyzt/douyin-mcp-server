const { request, uploadFile } = require('../../utils/request');
const { syncTabBarForRoute } = require('../../utils/tab');
const {
  SCENARIO_KINDS,
  ATTACHMENT_KINDS,
  QUICK_SCENARIOS,
  createUserMessage,
  createAssistantPlaceholder,
  isFutureScenario,
  buildChatRequestBody,
} = require('../../utils/chat-scenarios');

Page({
  data: {
    messages: [],
    input: '',
    loading: false,
    scenarios: QUICK_SCENARIOS,
    attachment: null,
    scrollIntoView: '',
    activeScenarioKind: SCENARIO_KINDS.KNOWLEDGE_QA,
  },

  onShow() {
    syncTabBarForRoute(this);
  },

  goSettings() {
    wx.navigateTo({ url: '/pages/settings/settings' });
  },

  onInput(e) {
    this.setData({ input: e.detail.value });
  },

  onScenarioTap(e) {
    const { id } = e.currentTarget.dataset;
    const scenario = QUICK_SCENARIOS.find((s) => s.id === id);
    if (!scenario) return;
    if (!scenario.enabled) {
      wx.showToast({ title: scenario.badge || '即将上线', icon: 'none' });
      return;
    }
    this.setData({
      input: scenario.prompt,
      activeScenarioKind: scenario.kind,
    });
    if (scenario.attachmentKind === ATTACHMENT_KINDS.DOCUMENT && !this.data.attachment) {
      wx.showToast({ title: '请先上传报价单', icon: 'none' });
      return;
    }
    this.send(scenario.kind);
  },

  chooseFile() {
    wx.chooseMessageFile({
      count: 1,
      type: 'file',
      success: async (res) => {
        const file = res.tempFiles[0];
        if (!file) return;
        try {
          const d = await uploadFile({
            url: '/api/documents/parse',
            filePath: file.path,
            name: 'file',
          });
          this.setData({
            attachment: {
              kind: ATTACHMENT_KINDS.DOCUMENT,
              filename: d.filename,
              text: d.text,
            },
            activeScenarioKind: SCENARIO_KINDS.QUOTE_REVIEW,
          });
          if (!this.data.input.trim()) {
            this.setData({ input: '帮我看报价单有没有漏项' });
          }
          wx.showToast({ title: '报价单已上传', icon: 'success' });
        } catch (e) {
          wx.showToast({ title: e.message || '上传失败', icon: 'none' });
        }
      },
    });
  },

  clearAttachment() {
    this.setData({ attachment: null });
  },

  async send(forcedKind) {
    const text = (this.data.input || '').trim();
    if (!text || this.data.loading) return;

    const kind = forcedKind || this.data.activeScenarioKind || SCENARIO_KINDS.KNOWLEDGE_QA;

    if (isFutureScenario(kind)) {
      const userMsg = createUserMessage({ text, kind, attachment: null });
      const assistantMsg = {
        ...createAssistantPlaceholder(kind),
        pending: false,
        content: '装修记账、预算管控和进度跟踪正在开发中，上线后你可以在这里用对话完成这些操作。',
      };
      const messages = this.data.messages.concat([userMsg, assistantMsg]);
      this.setData({ messages, input: '', attachment: null });
      this.scrollToBottom();
      return;
    }

    const userMsg = createUserMessage({
      text,
      kind,
      attachment: this.data.attachment,
    });
    const assistantMsg = createAssistantPlaceholder(kind);
    const messages = this.data.messages.concat([userMsg, assistantMsg]);
    const idx = messages.length - 1;

    this.setData({
      messages,
      input: '',
      loading: true,
      attachment: null,
      activeScenarioKind: SCENARIO_KINDS.KNOWLEDGE_QA,
    });
    this.scrollToBottom();

    try {
      const body = buildChatRequestBody(userMsg, userMsg.attachment);
      const d = await request({ url: '/api/chat', method: 'POST', data: body });
      messages[idx] = {
        ...assistantMsg,
        pending: false,
        content: d.answer,
        grounded: d.grounded,
        citations: d.citations || [],
        hasDocument: d.has_document,
      };
      this.setData({ messages });
    } catch (e) {
      messages[idx] = {
        ...assistantMsg,
        pending: false,
        content: e.message || '出错了，请稍后再试',
        error: true,
        grounded: false,
      };
      this.setData({ messages });
    } finally {
      this.setData({ loading: false });
      this.scrollToBottom();
    }
  },

  scrollToBottom() {
    this.setData({ scrollIntoView: 'chat-bottom' });
  },
});
