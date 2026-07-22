const { request } = require('../../utils/request');
const { syncTabBarForRoute } = require('../../utils/tab');
const { refreshUserContext, onLoginSuccess, onUserLogout } = require('../../utils/session');
const { mdExcerpt } = require('../../utils/markdown');
const { getSelectedModels } = require('../../utils/models');

Page({
  data: {
    needLogin: false,
    input: '',
    busy: false,
    step: 0,
    progress: 0,
    steps: ['正在读取视频', '正在整理重点', '已保存'],
    stepLabel: '',
    error: '',
    lastCard: null,
    displayName: '自装用户',
    quota: null,
    quotaPercent: 0,
    quotaExhausted: false,
  },

  onShow() {
    syncTabBarForRoute(this);
    refreshUserContext(this, { forceFetch: true });
  },

  onLoginSuccess() {
    onLoginSuccess(this, () => refreshUserContext(this, { forceFetch: true }));
  },

  onUserLogout() {
    onUserLogout(this);
  },

  onInput(e) {
    this.setData({ input: e.detail.value || '' });
  },

  pasteClipboard() {
    wx.getClipboardData({
      success: (res) => {
        if (res.data) this.setData({ input: res.data });
      },
    });
  },

  goSettings() {
    wx.navigateTo({ url: '/pages/settings/settings' });
  },

  goKnowledge() {
    wx.switchTab({ url: '/pages/knowledge/knowledge' });
  },

  isLikelyLink(text) {
    return /douyin|v\.douyin|iesdouyin/i.test(text || '');
  },

  withExcerpt(card) {
    if (!card) return null;
    const body = card.content_md || card.content || '';
    return { ...card, excerpt: mdExcerpt(body) };
  },

  async onSave() {
    const input = (this.data.input || '').trim();
    if (!input || this.data.busy) return;
    if (this.isLikelyLink(input) && this.data.quotaExhausted) {
      wx.showToast({ title: '今日链接收藏额度已用完，明天再来', icon: 'none' });
      return;
    }
    this.setData({
      busy: true,
      error: '',
      step: 0,
      progress: 5,
      stepLabel: this.data.steps[0],
      lastCard: null,
    });
    try {
      if (this.isLikelyLink(input)) {
        this.setData({ steps: ['正在读取视频', '正在整理重点', '已保存'] });
        await this.extractAndSave(input);
      } else {
        this.setData({
          steps: ['正在整理重点', '已保存'],
          step: 0,
          stepLabel: '正在整理重点',
        });
        await this.structureAndSave(input);
      }
    } catch (e) {
      this.setData({ error: e.message || '保存失败，请检查链接或稍后重试' });
      refreshUserContext(this);
    } finally {
      this.setData({ busy: false });
    }
  },

  async extractAndSave(url) {
    const models = getSelectedModels();
    const start = await request({
      url: '/api/video/extract',
      method: 'POST',
      data: { url, ...models },
    });
    const preview = await this.pollExtract(start.task_id);
    this.setData({ step: 1, progress: 75, stepLabel: this.data.steps[1] });
    const saved = await request({
      url: '/api/cards/save',
      method: 'POST',
      data: {
        title: preview.title,
        content_md: preview.content_md || preview.content,
        video_id: preview.video_id,
        source_url: preview.source_url || url,
        transcript: preview.transcript,
      },
    });
    this.setData({
      step: 2,
      progress: 100,
      stepLabel: this.data.steps[2],
      lastCard: this.withExcerpt(saved.card),
      input: '',
    });
    wx.showToast({ title: '已保存到知识库', icon: 'success' });
    refreshUserContext(this, { forceFetch: true });
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
              content_md: p.content_md || p.content || '',
              transcript: p.transcript || '',
              video_id: p.video_id || null,
              source_url: p.source_url || '',
            });
            return;
          }
          const step = t.status === 'structuring' ? 1 : 0;
          this.setData({
            progress: Math.max(this.data.progress, t.progress || 10),
            step,
            stepLabel: this.data.steps[step] || t.message || '',
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
    const models = getSelectedModels();
    const d = await request({
      url: '/api/cards/structure',
      method: 'POST',
      data: { text, llm_model: models.llm_model },
    });
    this.setData({
      step: 1,
      progress: 70,
      stepLabel: this.data.steps[1] || '正在整理重点',
    });
    const preview = d.preview || {};
    const saved = await request({
      url: '/api/cards/save',
      method: 'POST',
      data: {
        title: preview.title || '',
        content_md: preview.content_md || preview.content || text,
        transcript: text,
      },
    });
    this.setData({
      progress: 100,
      step: 1,
      stepLabel: '已保存',
      lastCard: this.withExcerpt(saved.card),
      input: '',
    });
    wx.showToast({ title: '已保存到知识库', icon: 'success' });
    refreshUserContext(this, { forceFetch: true });
  },
});
