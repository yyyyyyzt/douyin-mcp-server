const { request } = require('../../utils/request');
const { syncTabBarForRoute } = require('../../utils/tab');

const STAGES = ['全部', '水电', '防水', '泥木', '油漆', '验收', '其他'];

Page({
  data: {
    cards: [],
    filtered: [],
    loading: false,
    search: '',
    stage: '全部',
    stages: STAGES,
    detailVisible: false,
    detail: null,
    editing: false,
    editTitle: '',
    editBody: '',
  },

  onShow() {
    syncTabBarForRoute(this);
    this.loadCards();
  },

  goSettings() {
    wx.navigateTo({ url: '/pages/settings/settings' });
  },

  goCollect() {
    wx.switchTab({ url: '/pages/collect/collect' });
  },

  applyFilter() {
    let list = this.data.cards;
    const stage = this.data.stage;
    if (stage !== '全部') {
      if (stage === '其他') {
        const known = ['水电', '防水', '泥木', '油漆', '验收'];
        list = list.filter((c) => !known.some((k) => (c.stage || '').includes(k)));
      } else {
        list = list.filter((c) => (c.stage || '').includes(stage));
      }
    }
    const q = (this.data.search || '').trim().toLowerCase();
    if (q) {
      list = list.filter(
        (c) =>
          (c.title || '').toLowerCase().includes(q) ||
          (c.raw_text || '').toLowerCase().includes(q)
      );
    }
    this.setData({ filtered: list });
  },

  async loadCards() {
    this.setData({ loading: true });
    try {
      const d = await request({ url: '/api/cards' });
      this.setData({ cards: d.cards || [] }, () => this.applyFilter());
    } catch (e) {
      wx.showToast({ title: '加载失败', icon: 'none' });
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
    this.setData({
      detailVisible: true,
      detail: card,
      editing: false,
      editTitle: card.title || '',
      editBody: card.raw_text || '',
    });
  },

  closeDetail() {
    this.setData({ detailVisible: false, detail: null, editing: false });
  },

  onPopupVisibleChange(e) {
    if (!e.detail.visible) this.closeDetail();
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

  async saveDetail() {
    const card = this.data.detail;
    if (!card) return;
    try {
      await request({
        url: `/api/cards/${card.id}`,
        method: 'PUT',
        data: { title: this.data.editTitle, raw_text: this.data.editBody },
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
    const ok = await new Promise((resolve) => {
      wx.showModal({
        title: '确认删除',
        content: '确定删除这条知识？',
        success: (r) => resolve(r.confirm),
      });
    });
    if (!ok) return;
    try {
      await request({ url: `/api/cards/${card.id}`, method: 'DELETE' });
      wx.showToast({ title: '已删除', icon: 'success' });
      this.closeDetail();
      this.loadCards();
    } catch (e) {
      wx.showToast({ title: '删除失败', icon: 'none' });
    }
  },
});
