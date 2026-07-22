const config = require('./config');
const { validateApiBase } = require('./utils/api-config');

const API_BASE = String(config.API_BASE || '').trim().replace(/\/$/, '');
const apiConfigError = validateApiBase(API_BASE);

App({
  globalData: {
    apiBase: API_BASE,
    apiConfigError,
    loggedIn: false,
    needLogin: false,
  },
  onLaunch() {
    if (apiConfigError) {
      console.warn('[api-config]', apiConfigError);
      this.globalData.loggedIn = false;
      this.globalData.needLogin = true;
      return;
    }
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
      .catch((e) => {
        console.warn('[login]', (e && e.message) || e);
        this.globalData.loggedIn = false;
        this.globalData.needLogin = true;
      });
  },
});
