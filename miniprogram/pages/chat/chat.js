const { request, uploadFile } = require('../../utils/request');

const QUICK = [
  '卫生间防水要注意什么？',
  '帮我看报价单有没有漏项',
  '水电验收要检查哪些地方？',
];

Page({
  data: {
    messages: [],
    input: '',
    loading: false,
    quickQuestions: QUICK,
    document: null,
  },

  onInput(e) {
    this.setData({ input: e.detail.value });
  },

  askQuick(e) {
    this.setData({ input: e.currentTarget.dataset.q }, () => this.send());
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
            document: {
              filename: d.filename,
              text: d.text,
            },
          });
          if (!this.data.input.trim()) {
            this.setData({ input: '帮我看报价单有没有漏项' });
          }
        } catch (e) {
          wx.showToast({ title: e.message || '上传失败', icon: 'none' });
        }
      },
    });
  },

  clearDoc() {
    this.setData({ document: null });
  },

  async send() {
    const q = (this.data.input || '').trim();
    if (!q || this.data.loading) return;
    const userMsg = this.data.document
      ? `${q} [附件: ${this.data.document.filename}]`
      : q;
    const messages = this.data.messages.concat([
      { role: 'user', content: userMsg },
      { role: 'assistant', content: '', pending: true, grounded: true, citations: [] },
    ]);
    this.setData({ messages, input: '', loading: true });
    const idx = messages.length - 1;
    const body = { question: q };
    if (this.data.document) {
      body.document_text = this.data.document.text;
      body.document_name = this.data.document.filename;
    }
    try {
      const d = await request({ url: '/api/chat', method: 'POST', data: body });
      messages[idx] = {
        role: 'assistant',
        content: d.answer,
        grounded: d.grounded,
        citations: d.citations || [],
        hasDocument: d.has_document,
      };
      this.setData({ messages });
    } catch (e) {
      messages[idx] = {
        role: 'assistant',
        content: e.message || '出错了，请稍后再试',
        error: true,
      };
      this.setData({ messages });
    } finally {
      this.setData({ loading: false });
    }
  },
});
