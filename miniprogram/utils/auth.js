/** 登录与 token（自包含，不依赖 request，避免循环依赖） */

const { getApiBase, validateApiBase } = require('./api-config');

const TOKEN_KEY = 'auth_token';

function getToken() {
  try {
    return wx.getStorageSync(TOKEN_KEY) || '';
  } catch (e) {
    return '';
  }
}

function setToken(token) {
  try {
    wx.setStorageSync(TOKEN_KEY, token || '');
  } catch (e) {
    /* ignore */
  }
}

function clearToken() {
  try {
    wx.removeStorageSync(TOKEN_KEY);
  } catch (e) {
    /* ignore */
  }
}

function formatRequestError(err) {
  const msg = (err && err.errMsg) || '';
  if (!msg) return '网络错误，请检查手机网络';
  if (msg.includes('url not in domain list')) {
    return '域名未加入微信小程序 request 合法域名，请在公众平台配置 HTTPS 域名';
  }
  if (msg.includes('fail ssl') || msg.includes('certificate')) {
    return 'HTTPS 证书无效，请检查服务器证书';
  }
  if (msg.includes('timeout')) {
    return '连接超时，请确认服务器可访问';
  }
  return msg;
}

function wechatLogin() {
  const base = getApiBase();
  const configError = validateApiBase(base);
  if (configError) {
    return Promise.reject(new Error(configError));
  }

  return new Promise((resolve, reject) => {
    wx.login({
      success: (res) => {
        if (!res.code) {
          reject(new Error('微信未返回登录 code，请重试'));
          return;
        }
        wx.request({
          url: `${base}/api/auth/wechat/login`,
          method: 'POST',
          data: { code: res.code },
          header: { 'Content-Type': 'application/json' },
          success: (resp) => {
            if (resp.statusCode >= 400) {
              const detail = resp.data && resp.data.detail;
              reject(new Error(typeof detail === 'string' ? detail : `登录失败(${resp.statusCode})`));
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
          fail: (err) => {
            reject(new Error(formatRequestError(err)));
          },
        });
      },
      fail: (err) => {
        reject(new Error(formatRequestError(err) || '微信登录失败'));
      },
    });
  });
}

async function ensureLogin() {
  if (getToken()) return getToken();
  const data = await wechatLogin();
  return data.token;
}

module.exports = {
  TOKEN_KEY,
  getToken,
  setToken,
  clearToken,
  wechatLogin,
  ensureLogin,
};
