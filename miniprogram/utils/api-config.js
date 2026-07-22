/** API 地址读取与校验（登录 / 请求共用） */

const PLACEHOLDER_HOST = 'your-api.example.com';

function normalizeBase(base) {
  return String(base || '').trim().replace(/\/$/, '');
}

function getApiBase() {
  try {
    const app = getApp();
    if (app && app.globalData && app.globalData.apiBase) {
      return normalizeBase(app.globalData.apiBase);
    }
  } catch (e) {
    /* 模块初始化阶段 getApp 可能不可用 */
  }
  try {
    return normalizeBase(require('../config').API_BASE);
  } catch (e) {
    return '';
  }
}

function validateApiBase(base) {
  const url = normalizeBase(base);
  if (!url) {
    return '未配置后端：请修改 miniprogram/config.js 中的 API_BASE';
  }
  if (url.includes(PLACEHOLDER_HOST)) {
    return '请将 config.js 的 API_BASE 改为你服务器的 HTTPS 地址';
  }
  if (!/^https:\/\//i.test(url)) {
    return '手机预览需 HTTPS 地址，并在微信公众平台配置 request 合法域名';
  }
  return '';
}

module.exports = {
  PLACEHOLDER_HOST,
  getApiBase,
  validateApiBase,
};
