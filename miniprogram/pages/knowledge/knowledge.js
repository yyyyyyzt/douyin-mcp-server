const { request } = require('../../utils/request');
const { syncTabBarForRoute } = require('../../utils/tab');
const { refreshLoginState, onLoginSuccess } = require('../../utils/session');
const { mdToNodes, mdExcerpt } = require('../../utils/markdown');

const STAGE_OPTIONS = ['水电', '防水', '泥木', '油漆', '验收', '拆改', '其他'];
const KNOWN_STAGES = ['水电', '防水', '泥木', '油漆', '验收', '拆改'];

function cardBody(c) {
  return c.content_md || c.content || '';
}

function normalizeStage(stage) {
  const s = (stage || '').trim();
  if (!s) return '其他';
  for (const k of KNOWN_STAGES) {
    if (s.includes(k)) return k;
  }
  return '其他';
}

Page({
  data: {
    needLogin: false,
    cards: [],
    sections: [],
    stageFilters: [],
    loading: false,
    search: '',
    stage: '全部',
    detailVisible: false,
    detail: null,
    detailHtml: '',
    editing: false,
    editTitle: '',
    editBody: '',
    editStageIndex: 5,
    stageOptions: STAGE_OPTIONS,
  },

  onShow() {
    syncTabBarForRoute(this);
    if (refreshLoginState(this)) {
      this.loadCards();
    }
  },

  onLoginSuccess() {
    onLoginSuccess(this, () => this.loadCards());
  },

  noop() {},

  goSettings() {
    wx.navigateTo({ url: '/pages/settings/settings' });
  },

  goCollect() {
    wx.switchTab({ url: '/pages/collect/collect' });
  },

  buildFilters(cards) {
    const counts = { 全部: cards.length };
    STAGE_OPTIONS.forEach((s) => {
      counts[s] = 0;
    });
    cards.forEach((c) => {
      const key = normalizeStage(c.stage);
      counts[key] = (counts[key] || 0) + 1;
    });
    const filters = [{ key: '全部', label: '全部', count: counts['全部'] || 0 }];
    STAGE_OPTIONS.forEach((s) => {
      filters.push({ key: s, label: s, count: counts[s] || 0 });
    });
    return filters;
  },

  applyFilter() {
    const q = (this.data.search || '').trim().toLowerCase();
    let list = this.data.cards.map((c) => {
      const stageLabel = normalizeStage(c.stage);
      return {
        ...c,
        stageLabel,
        excerpt: mdExcerpt(cardBody(c)),
      };
    });

    if (this.data.stage !== '全部') {
      list = list.filter((c) => c.stageLabel === this.data.stage);
    }
    if (q) {
      list = list.filter(
        (c) =>
          (c.title || '').toLowerCase().includes(q) ||
          cardBody(c).toLowerCase().includes(q) ||
          c.stageLabel.toLowerCase().includes(q)
      );
    }

    const order = this.data.stage === '全部' ? STAGE_OPTIONS : [this.data.stage];
    const sections = [];
    order.forEach((label) => {
      const cards = list.filter((c) => c.stageLabel === label);
      if (cards.length) {
        sections.push({ key: label, label, cards });
      }
    });

    this.setData({
      sections,
      stageFilters: this.buildFilters(this.data.cards),
    });
  },

  async loadCards() {
    this.setData({ loading: true });
    try {
      const d = await request({ url: '/api/cards' });
      this.setData({ cards: d.cards || [] }, () => this.applyFilter());
    } catch (e) {
      refreshLoginState(this);
      wx.showToast({ title: e.message || '加载失败', icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
  },

  onSearchChange(e) {
    this.setData({ search: e.detail.value || '' }, () => this.applyFilter());
  },

  onSearchClear() {
    this.setData({ search: '' }, () => this.applyFilter());
  },

  onStageTap(e) {
    this.setData({ stage: e.currentTarget.dataset.stage }, () => this.applyFilter());
  },

  openDetail(e) {
    const id = e.currentTarget.dataset.id;
    const card = this.data.cards.find((c) => c.id === id);
    if (!card) return;
    const body = cardBody(card);
    const stageLabel = normalizeStage(card.stage);
    const editStageIndex = Math.max(0, STAGE_OPTIONS.indexOf(stageLabel));
    this.setData({
      detailVisible: true,
      detail: { ...card, stageLabel },
      detailHtml: mdToNodes(body),
      editing: false,
      editTitle: card.title || '',
      editBody: body,
      editStageIndex,
    });
  },

  closeDetail() {
    this.setData({ detailVisible: false, detail: null, editing: false, detailHtml: '' });
  },

  toggleEdit() {
    this.setData({ editing: true });
  },

  onEditTitle(e) {
    this.setData({ editTitle: e.detail.value });
  },

  onEditBody(e) {
    this.setData({ editBody: e.detail.value || '' });
  },

  onEditStage(e) {
    this.setData({ editStageIndex: Number(e.detail.value) || 0 });
  },

  async saveDetail() {
    const card = this.data.detail;
    if (!card) return;
    const stage = STAGE_OPTIONS[this.data.editStageIndex] || '其他';
    try {
      await request({
        url: `/api/cards/${card.id}`,
        method: 'PUT',
        data: {
          title: this.data.editTitle,
          content_md: this.data.editBody,
          stage,
        },
      });
      wx.showToast({ title: '已保存', icon: 'success' });
      this.closeDetail();
      this.loadCards();
    } catch (e) {
      wx.showToast({ title: e.message || '保存失败', icon: 'none' });
    }
  },

  async deleteDetail() {
    const card = this.data.detail;
    if (!card) return;
    const that = this;
    wx.showModal({
      title: '确认删除',
      content: '删除后不可恢复',
      success: async (res) => {
        if (!res.confirm) return;
        try {
          await request({ url: `/api/cards/${card.id}`, method: 'DELETE' });
          wx.showToast({ title: '已删除', icon: 'success' });
          that.closeDetail();
          that.loadCards();
        } catch (e) {
          wx.showToast({ title: e.message || '删除失败', icon: 'none' });
        }
      },
    });
  },
});
