const auth = require('./auth');

function getBaseUrl() {
  const app = getApp();
  return (app && app.globalData.apiBase) || '';
}

function request({ url, method = 'GET', data, header = {}, auth = true }) {
  const base = getBaseUrl();
  const headers = { 'Content-Type': 'application/json', ...header };
  if (auth) {
    const token = auth.getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  return new Promise((resolve, reject) => {
    wx.request({
      url: base + url,
      method,
      data,
      header: headers,
      success: (res) => {
        if (res.statusCode === 401 && auth) {
          auth.clearToken();
          reject(new Error('登录已过期'));
          return;
        }
        if (res.statusCode >= 400) {
          reject(new Error((res.data && res.data.detail) || '请求失败'));
          return;
        }
        resolve(res.data);
      },
      fail: reject,
    });
  });
}

function uploadFile({ url, filePath, name = 'file', formData = {} }) {
  const base = getBaseUrl();
  const token = auth.getToken();
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
        if (res.statusCode >= 400) {
          reject(new Error(data.detail || '上传失败'));
          return;
        }
        resolve(data);
      },
      fail: reject,
    });
  });
}

module.exports = { request, uploadFile, getBaseUrl };
