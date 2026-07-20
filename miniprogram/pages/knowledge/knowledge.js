const { request } = require('../../utils/request');
const { syncTabBarForRoute } = require('../../utils/tab');
const { refreshLoginState, onLoginSuccess } = require('../../utils/session');
const { mdToNodes, mdExcerpt } = require('../../utils/markdown');

const STAGES = ['全部', '水电', '防水', '泥木', '油漆', '验收', '其他'];

function cardBody(c) {
  return c.content_md || c.content || '';
}

Page({
  data: {
    needLogin: false,
    cards: [],
    filtered: [],
    loading: false,
    search: '',
    stage: '全部',
    stages: STAGES,
    detailVisible: false,
    detail: null,
    detailHtml: '',
    editing: false,
    editTitle: '',
    editBody: '',
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
          cardBody(c).toLowerCase().includes(q)
      );
    }
    this.setData({
      filtered: list.map((c) => ({
        ...c,
        excerpt: mdExcerpt(cardBody(c)),
      })),
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
    this.setData({
      detailVisible: true,
      detail: card,
      detailHtml: mdToNodes(body),
      editing: false,
      editTitle: card.title || '',
      editBody: body,
    });
  },

  closeDetail() {
    this.setData({ detailVisible: false, detail: null, editing: false, detailHtml: '' });
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
        data: { title: this.data.editTitle, content_md: this.data.editBody },
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
