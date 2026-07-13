Page({
  data: {
    apiBase: '',
  },

  onShow() {
    const app = getApp();
    this.setData({ apiBase: app.globalData.apiBase || '' });
  },

  openSettings() {
    wx.showToast({ title: '模型设置请在服务端配置', icon: 'none' });
  },
});
