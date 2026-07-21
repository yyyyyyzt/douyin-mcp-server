/** HTTP 封装：token 直接读本地存储，不 require auth（避免循环依赖） */

const TOKEN_KEY = 'auth_token';

function getToken() {
  try {
    return wx.getStorageSync(TOKEN_KEY) || '';
  } catch (e) {
    return '';
  }
}

function clearToken() {
  try {
    wx.removeStorageSync(TOKEN_KEY);
  } catch (e) {
    /* ignore */
  }
}

function getBaseUrl() {
  const app = getApp();
  return (app && app.globalData && app.globalData.apiBase) || '';
}

function markNeedLogin() {
  const app = getApp();
  if (app && app.globalData) {
    app.globalData.loggedIn = false;
    app.globalData.needLogin = true;
  }
}

function request({ url, method = 'GET', data, header = {}, needAuth = true }) {
  const base = getBaseUrl();
  const headers = { 'Content-Type': 'application/json', ...header };
  if (needAuth) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  return new Promise((resolve, reject) => {
    wx.request({
      url: base + url,
      method,
      data,
      header: headers,
      success: (res) => {
        if (res.statusCode === 401 && needAuth) {
          clearToken();
          markNeedLogin();
          reject(new Error('请先登录'));
          return;
        }
        if (res.statusCode === 429) {
          reject(new Error((res.data && res.data.detail) || '今日次数已用完'));
          return;
        }
        if (res.statusCode >= 400) {
          const detail = res.data && res.data.detail;
          reject(new Error(typeof detail === 'string' ? detail : '请求失败'));
          return;
        }
        resolve(res.data);
      },
      fail: (err) => {
        reject(new Error((err && err.errMsg) || '网络错误'));
      },
    });
  });
}

function uploadFile({ url, filePath, name = 'file', formData = {} }) {
  const base = getBaseUrl();
  const token = getToken();
  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: base + url,
      filePath,
      name,
      formData,
      header: token ? { Authorization: `Bearer ${token}` } : {},
      success: (res) => {
        let data = {};
        try {
          data = JSON.parse(res.data || '{}');
        } catch (e) {
          reject(new Error('响应解析失败'));
          return;
        }
        if (res.statusCode === 401) {
          clearToken();
          markNeedLogin();
          reject(new Error('请先登录'));
          return;
        }
        if (res.statusCode >= 400) {
          reject(new Error(data.detail || '上传失败'));
          return;
        }
        resolve(data);
      },
      fail: (err) => {
        reject(new Error((err && err.errMsg) || '上传失败'));
      },
    });
  });
}

module.exports = { request, uploadFile, getBaseUrl, markNeedLogin };
