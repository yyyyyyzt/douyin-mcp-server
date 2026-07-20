const auth = require('../../utils/auth');

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