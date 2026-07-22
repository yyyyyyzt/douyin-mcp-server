const auth = require('../../utils/auth');
const { validateApiBase, getApiBase } = require('../../utils/api-config');

Component({
  properties: {
    visible: { type: Boolean, value: false },
  },
  data: {
    loading: false,
    error: '',
    configError: '',
    apiBase: '',
  },
  observers: {
    visible(v) {
      if (!v) return;
      const base = getApiBase();
      const configError = validateApiBase(base);
      this.setData({
        apiBase: base,
        configError,
        error: configError || '',
      });
    },
  },
  methods: {
    async onLogin() {
      if (this.data.loading) return;
      const configError = validateApiBase(getApiBase());
      if (configError) {
        this.setData({ error: configError, configError });
        return;
      }
      this.setData({ loading: true, error: '' });
      try {
        await auth.wechatLogin();
        const app = getApp();
        if (app && app.globalData) {
          app.globalData.loggedIn = true;
          app.globalData.needLogin = false;
          app.globalData.apiConfigError = '';
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
