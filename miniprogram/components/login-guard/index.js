const auth = require('../../utils/auth');
const user = require('../../utils/user');

Component({
  properties: {
    visible: { type: Boolean, value: false },
  },
  data: {
    loading: false,
    error: '',
  },
  methods: {
    async onLogin() {
      if (this.data.loading) return;
      this.setData({ loading: true, error: '' });
      try {
        await auth.wechatLogin();
        await user.syncWechatProfile();
        try {
          await user.fetchProfile();
        } catch (e) {
          /* 已有登录响应中的基础资料即可 */
        }
        const app = getApp();
        if (app && app.globalData) {
          app.globalData.loggedIn = true;
          app.globalData.needLogin = false;
        }
        this.triggerEvent('success');
      } catch (e) {
        this.setData({ error: (e && e.message) || '登录失败，请重试' });
      } finally {
        this.setData({ loading: false });
      }
    },
  },
});
