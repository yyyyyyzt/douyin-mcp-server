/** 全局配置：在开发者工具中可改为本机后端地址 */
const API_BASE = 'https://your-api.example.com';

App({
  globalData: {
    apiBase: API_BASE,
  },
  onLaunch() {
    const auth = require('./utils/auth');
    auth.ensureLogin().catch(() => {
      wx.showModal({
        title: '服务未就绪',
        content: '暂时无法连接服务器，请稍后再试',
        showCancel: false,
      });
    });
  },
});
