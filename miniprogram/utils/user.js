/** 用户资料、额度与退出登录 */

const { request, uploadFile, getBaseUrl } = require('./request');
const { clearToken } = require('./auth');

const USER_KEY = 'user_profile';
const QUOTA_KEY = 'user_quota';

function getDisplayName(user) {
  if (!user) return '自装用户';
  const name = (user.display_name || user.nickname || '').trim();
  if (name) return name;
  if (user.id) return `用户${user.id}`;
  return '自装用户';
}

function getAvatarInitial(user) {
  const name = getDisplayName(user);
  return name.slice(0, 1) || '友';
}

function resolveAvatarUrl(avatarUrl) {
  const url = (avatarUrl || '').trim();
  if (!url) return '';
  if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('wxfile://')) {
    return url;
  }
  if (url.startsWith('/')) {
    const base = getBaseUrl().replace(/\/$/, '');
    return base ? `${base}${url}` : url;
  }
  return url;
}

function isLocalAvatarPath(path) {
  const p = (path || '').trim();
  if (!p) return false;
  return (
    p.startsWith('wxfile://') ||
    p.startsWith('http://tmp/') ||
    p.startsWith('https://tmp/') ||
    (!p.startsWith('http://') && !p.startsWith('https://') && !p.startsWith('/static/'))
  );
}

function setUserCache(user) {
  try {
    wx.setStorageSync(USER_KEY, user || null);
  } catch (e) {
    /* ignore */
  }
}

function getUserCache() {
  try {
    return wx.getStorageSync(USER_KEY) || null;
  } catch (e) {
    return null;
  }
}

function setQuotaCache(quota) {
  try {
    wx.setStorageSync(QUOTA_KEY, quota || null);
  } catch (e) {
    /* ignore */
  }
}

function getQuotaCache() {
  try {
    return wx.getStorageSync(QUOTA_KEY) || null;
  } catch (e) {
    return null;
  }
}

function clearUserCache() {
  try {
    wx.removeStorageSync(USER_KEY);
    wx.removeStorageSync(QUOTA_KEY);
  } catch (e) {
    /* ignore */
  }
}

function applyLoginData(data) {
  const app = getApp();
  const user = (data && data.user) || null;
  const quota = (data && data.quota) || null;
  if (app && app.globalData) {
    app.globalData.user = user;
    app.globalData.quota = quota;
  }
  if (user) setUserCache(user);
  if (quota) setQuotaCache(quota);
}

function getContext() {
  const app = getApp();
  const user = (app && app.globalData && app.globalData.user) || getUserCache();
  const quota = (app && app.globalData && app.globalData.quota) || getQuotaCache();
  return { user, quota };
}

function buildPageUserState() {
  const { user, quota } = getContext();
  const limit = quota && quota.extract_limit ? quota.extract_limit : 0;
  const used = quota && quota.extract_used != null ? quota.extract_used : 0;
  const quotaPercent = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  return {
    displayName: getDisplayName(user),
    avatarUrl: resolveAvatarUrl(user && user.avatar_url),
    avatarInitial: getAvatarInitial(user),
    quota,
    quotaPercent,
    quotaExhausted: !!(quota && quota.extract_remaining === 0),
  };
}

function syncPageUser(page) {
  if (page && typeof page.setData === 'function') {
    page.setData(buildPageUserState());
  }
}

function syncComponentUser(component) {
  if (component && typeof component.setData === 'function') {
    component.setData(buildPageUserState());
  }
}

async function fetchProfile() {
  const data = await request({ url: '/api/me' });
  applyLoginData(data);
  return data;
}

async function updateProfile({ nickname, avatarUrl }) {
  const data = await request({
    url: '/api/me',
    method: 'PUT',
    data: {
      nickname: nickname || '',
      avatar_url: avatarUrl || '',
    },
  });
  applyLoginData(data);
  return data;
}

async function uploadAvatar(filePath) {
  const data = await uploadFile({
    url: '/api/me/avatar',
    filePath,
    name: 'file',
  });
  applyLoginData(data);
  return data;
}

async function saveProfile({ nickname, avatarPath }) {
  const name = (nickname || '').trim();
  if (!name) {
    throw new Error('请输入昵称');
  }
  let avatarUrl = '';
  if (avatarPath && isLocalAvatarPath(avatarPath)) {
    const uploaded = await uploadAvatar(avatarPath);
    avatarUrl = (uploaded.user && uploaded.user.avatar_url) || '';
  } else if (avatarPath) {
    avatarUrl = avatarPath;
  }
  return updateProfile({ nickname: name, avatarUrl });
}

function logout() {
  clearToken();
  clearUserCache();
  const app = getApp();
  if (app && app.globalData) {
    app.globalData.loggedIn = false;
    app.globalData.needLogin = true;
    app.globalData.user = null;
    app.globalData.quota = null;
  }
}

module.exports = {
  getDisplayName,
  resolveAvatarUrl,
  applyLoginData,
  fetchProfile,
  updateProfile,
  uploadAvatar,
  saveProfile,
  syncPageUser,
  syncComponentUser,
  buildPageUserState,
  logout,
};
