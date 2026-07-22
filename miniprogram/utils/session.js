/** 页面登录态与用户上下文 */

function refreshLoginState(page) {
  const app = getApp();
  const loggedIn = !!(app && app.globalData && app.globalData.loggedIn);
  const needLogin = !!(app && app.globalData && app.globalData.needLogin);
  page.setData({ needLogin: needLogin || !loggedIn });
  return loggedIn && !needLogin;
}

async function refreshUserContext(page, options) {
  const forceFetch = !!(options && options.forceFetch);
  if (!refreshLoginState(page)) return false;
  const user = require('./user');
  user.syncPageUser(page);
  if (forceFetch || !getApp().globalData.user) {
    try {
      await user.fetchProfile();
      user.syncPageUser(page);
    } catch (e) {
      /* 网络失败时仍展示缓存昵称 */
    }
  }
  return true;
}

function onLoginSuccess(page, afterLogin) {
  const app = getApp();
  if (app && app.globalData) {
    app.globalData.loggedIn = true;
    app.globalData.needLogin = false;
  }
  page.setData({ needLogin: false });
  const user = require('./user');
  user.syncPageUser(page);
  if (typeof afterLogin === 'function') afterLogin();
}

function onUserLogout(page) {
  page.setData({ needLogin: true });
}

module.exports = {
  refreshLoginState,
  refreshUserContext,
  onLoginSuccess,
  onUserLogout,
};
