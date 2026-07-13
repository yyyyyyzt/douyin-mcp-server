const TOKEN_KEY = 'auth_token';
const { request } = require('./request');

function getToken() {
  return wx.getStorageSync(TOKEN_KEY) || '';
}

function setToken(token) {
  wx.setStorageSync(TOKEN_KEY, token);
}

function clearToken() {
  wx.removeStorageSync(TOKEN_KEY);
}

function wechatLogin() {
  return new Promise((resolve, reject) => {
    wx.login({
      success: async (res) => {
        if (!res.code) {
          reject(new Error('微信登录失败'));
          return;
        }
        try {
          const data = await request({
            url: '/api/auth/wechat/login',
            method: 'POST',
            data: { code: res.code },
            auth: false,
          });
          if (data.token) {
            setToken(data.token);
            resolve(data);
          } else {
            reject(new Error('未获取到登录凭证'));
          }
        } catch (e) {
          reject(e);
        }
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
