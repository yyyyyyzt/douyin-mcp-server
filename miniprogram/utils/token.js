/** Token 存取（独立模块，避免 auth ↔ request 循环依赖） */
const TOKEN_KEY = 'auth_token';

function getToken() {
  try {
    return wx.getStorageSync(TOKEN_KEY) || '';
  } catch (e) {
    return '';
  }
}

function setToken(token) {
  wx.setStorageSync(TOKEN_KEY, token || '');
}

function clearToken() {
  try {
    wx.removeStorageSync(TOKEN_KEY);
  } catch (e) {
    /* ignore */
  }
}

module.exports = { TOKEN_KEY, getToken, setToken, clearToken };
