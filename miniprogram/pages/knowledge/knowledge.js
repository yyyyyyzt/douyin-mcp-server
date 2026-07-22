const { request } = require('../../utils/request');
const { syncTabBarForRoute } = require('../../utils/tab');
const { refreshUserContext, onLoginSuccess, onUserLogout } = require('../../utils/session');
const { mdToNodes, mdExcerpt } = require('../../utils/markdown');

function cardBody(c) {
  return c.content_md || c.content || '';
}

Page({
  data: {
    needLogin: false,
    cards: [],
    displayCards: [],
    loading: false,
    search: '',
    detailVisible: false,
    detail: null,
    detailHtml: '',
    editing: false,
    editTitle: '',
    editBody: '',
  },

  onShow() {
    syncTabBarForRoute(this);
    refreshUserContext(this, { forceFetch: true }).then((ok) => {
      if (ok) this.loadCards();
    });
  },

  onLoginSuccess() {
    onLoginSuccess(this, () => {
      refreshUserContext(this, { forceFetch: true });
      this.loadCards();
    });
  },

  onUserLogout() {
    onUserLogout(this);
  },

  noop() {},

  goSettings() {
    wx.navigateTo({ url: '/pages/settings/settings' });
  },

  goCollect() {
    wx.switchTab({ url: '/pages/collect/collect' });
  },

  applyFilter() {
    const q = (this.data.search || '').trim().toLowerCase();
    let list = this.data.cards.map((c) => ({
      ...c,
      excerpt: mdExcerpt(cardBody(c)),
    }));

    if (q) {
      list = list.filter(
        (c) =>
          (c.title || '').toLowerCase().includes(q) ||
          cardBody(c).toLowerCase().includes(q)
      );
    }

    this.setData({ displayCards: list });
  },

  async loadCards() {
    this.setData({ loading: true });
    try {
      const d = await request({ url: '/api/cards' });
      this.setData({ cards: d.cards || [] }, () => this.applyFilter());
    } catch (e) {
      refreshUserContext(this);
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

  openDetail(e) {
    const id = e.currentTarget.dataset.id;
    const card = this.data.cards.find((c) => c.id === id);
    if (!card) return;
    this.showDetail(card);
  },

  showDetail(card) {
    const body = cardBody(card);
    this.setData({
      detailVisible: true,
      detail: { ...card },
      detailHtml: mdToNodes(body),
      editing: false,
      editTitle: card.title || '',
      editBody: body,
    });
  },

  openCardMenu(e) {
    const id = e.currentTarget.dataset.id;
    const card = this.data.cards.find((c) => c.id === id);
    if (!card) return;
    wx.showActionSheet({
      itemList: ['查看详情', '编辑', '删除'],
      success: (res) => {
        if (res.tapIndex === 0) {
          this.showDetail(card);
        } else if (res.tapIndex === 1) {
          this.showDetail(card);
          this.setData({ editing: true });
        } else if (res.tapIndex === 2) {
          this.showDetail(card);
          this.deleteDetail();
        }
      },
    });
  },

  closeDetail() {
    this.setData({ detailVisible: false, detail: null, editing: false, detailHtml: '' });
  },

  toggleEdit() {
    this.setData({ editing: true });
  },

  cancelEdit() {
    const card = this.data.detail;
    if (!card) {
      this.setData({ editing: false });
      return;
    }
    this.setData({
      editing: false,
      editTitle: card.title || '',
      editBody: cardBody(card),
    });
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
        data: {
          title: this.data.editTitle,
          content_md: this.data.editBody,
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
