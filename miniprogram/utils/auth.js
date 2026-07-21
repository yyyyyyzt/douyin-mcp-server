const { getToken, setToken, clearToken } = require('./token');

function getBaseUrl() {
  const app = getApp();
  return (app && app.globalData && app.globalData.apiBase) || '';
}

function wechatLogin() {
  return new Promise((resolve, reject) => {
    wx.login({
      success: (res) => {
        if (!res.code) {
          reject(new Error('微信登录失败'));
          return;
        }
        const base = getBaseUrl();
        wx.request({
          url: `${base}/api/auth/wechat/login`,
          method: 'POST',
          data: { code: res.code },
          header: { 'Content-Type': 'application/json' },
          success: (resp) => {
            if (resp.statusCode >= 400) {
              const detail = resp.data && resp.data.detail;
              reject(new Error(typeof detail === 'string' ? detail : '登录失败'));
              return;
            }
            const data = resp.data || {};
            if (!data.token) {
              reject(new Error('未获取到登录凭证'));
              return;
            }
            setToken(data.token);
            resolve(data);
          },
          fail: reject,
        });
      },
      fail: reject,
    });
  });
}

async function ensureLogin() {
  if (getToken()) return getToken();
  const data = await wechatLogin();
  return data.token;
}

module.exports = {
  getToken,
  setToken,
  clearToken,
  wechatLogin,
  ensureLogin,
};
