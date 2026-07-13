const { request } = require('../../utils/request');

Page({
  data: {
    input: '',
    busy: false,
    step: 0,
    progress: 0,
    steps: ['正在读取视频', '正在整理重点', '已保存'],
    error: '',
    lastCard: null,
  },

  onInput(e) {
    this.setData({ input: e.detail.value });
  },

  pasteClipboard() {
    wx.getClipboardData({
      success: (res) => {
        if (res.data) this.setData({ input: res.data });
      },
    });
  },

  isLikelyLink(text) {
    return /douyin|v\.douyin|iesdouyin/i.test(text || '');
  },

  async onSave() {
    const input = (this.data.input || '').trim();
    if (!input || this.data.busy) return;
    this.setData({ busy: true, error: '', step: 0, progress: 5 });
    try {
      if (this.isLikelyLink(input)) {
        await this.extractAndSave(input);
      } else {
        this.setData({ steps: ['正在整理重点', '已保存'], step: 0 });
        await this.structureAndSave(input);
      }
    } catch (e) {
      this.setData({ error: e.message || '保存失败' });
    } finally {
      this.setData({ busy: false });
    }
  },

  async extractAndSave(url) {
    const start = await request({
      url: '/api/video/extract',
      method: 'POST',
      data: { url },
    });
    const preview = await this.pollExtract(start.task_id);
    this.setData({ step: 1, progress: 75 });
    const saved = await request({
      url: '/api/cards/save',
      method: 'POST',
      data: {
        title: preview.title,
        content: preview.content,
        video_id: preview.video_id,
        source_url: preview.source_url || url,
        transcript: preview.transcript,
      },
    });
    this.setData({ step: 2, progress: 100, lastCard: saved.card, input: '' });
    wx.showToast({ title: '已保存', icon: 'success' });
  },

  pollExtract(taskId) {
    return new Promise((resolve, reject) => {
      const tick = async () => {
        try {
          const d = await request({ url: `/api/video/extract/task/${taskId}` });
          const t = d.task;
          if (t.status === 'failed') {
            reject(new Error(t.error || '读取失败'));
            return;
          }
          if (t.status === 'done') {
            const p = t.preview || {};
            resolve({
              title: p.title || '',
              content: p.content || '',
              transcript: p.transcript || '',
              video_id: p.video_id || null,
              source_url: p.source_url || '',
            });
            return;
          }
          this.setData({
            progress: Math.max(this.data.progress, t.progress || 10),
            step: t.status === 'structuring' ? 1 : 0,
          });
        } catch (e) {
          /* retry */
        }
        setTimeout(tick, 1000);
      };
      tick();
    });
  },

  async structureAndSave(text) {
    const d = await request({
      url: '/api/cards/structure',
      method: 'POST',
      data: { text },
    });
    this.setData({ step: 1, progress: 70 });
    const saved = await request({
      url: '/api/cards/save',
      method: 'POST',
      data: {
        title: d.preview?.title || '',
        content: d.preview?.content || text,
        transcript: text,
      },
    });
    this.setData({ progress: 100, step: 1, lastCard: saved.card, input: '' });
    wx.showToast({ title: '已保存', icon: 'success' });
  },
});
