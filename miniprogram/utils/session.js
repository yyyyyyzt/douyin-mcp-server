/** 页面登录态检查：未登录时展示 login-guard。 */

function refreshLoginState(page) {
  const app = getApp();
  const loggedIn = !!(app && app.globalData && app.globalData.loggedIn);
  const needLogin = !!(app && app.globalData && app.globalData.needLogin);
  page.setData({ needLogin: needLogin || !loggedIn });
  return loggedIn && !needLogin;
}

function onLoginSuccess(page, afterLogin) {
  const app = getApp();
  if (app && app.globalData) {
    app.globalData.loggedIn = true;
    app.globalData.needLogin = false;
  }
  page.setData({ needLogin: false });
  if (typeof afterLogin === 'function') afterLogin();
}

module.exports = { refreshLoginState, onLoginSuccess };
