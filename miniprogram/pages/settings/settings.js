Page({
  data: {
    apiBase: '',
  },

  onShow() {
    const app = getApp();
    this.setData({ apiBase: (app && app.globalData.apiBase) || '' });
  },
});
