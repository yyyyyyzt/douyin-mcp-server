/** 全局配置：在开发者工具中可改为本机后端地址 */
const API_BASE = 'https://your-api.example.com';

App({
  globalData: {
    apiBase: API_BASE,
    loggedIn: false,
    needLogin: false,
  },
  onLaunch() {
    const auth = require('./utils/auth');
    if (auth.getToken()) {
      this.globalData.loggedIn = true;
      this.globalData.needLogin = false;
      return;
    }
    auth
      .ensureLogin()
      .then(() => {
        this.globalData.loggedIn = true;
        this.globalData.needLogin = false;
      })
      .catch(() => {
        this.globalData.loggedIn = false;
        this.globalData.needLogin = true;
      });
  },
});
