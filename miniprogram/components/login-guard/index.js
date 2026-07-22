const auth = require('../../utils/auth');
const user = require('../../utils/user');

Component({
  properties: {
    visible: { type: Boolean, value: false },
  },
  data: {
    loading: false,
    error: '',
    avatarPath: '',
    nickname: '',
  },
  methods: {
    onChooseAvatar(e) {
      const path = (e.detail && e.detail.avatarUrl) || '';
      if (path) {
        this.setData({ avatarPath: path, error: '' });
      }
    },

    onNicknameInput(e) {
      this.setData({
        nickname: (e.detail && e.detail.value) || '',
        error: '',
      });
    },

    onNicknameReview(e) {
      const pass = !!(e.detail && e.detail.pass);
      const nickname = ((e.detail && e.detail.value) || '').trim();
      if (pass && nickname) {
        this.setData({ nickname, error: '' });
      }
    },

    async onSubmit() {
      if (this.data.loading) return;

      const nickname = (this.data.nickname || '').trim();
      if (!nickname) {
        this.setData({ error: '请先填写昵称' });
        return;
      }

      this.setData({ loading: true, error: '' });
      try {
        await auth.wechatLogin();
        await user.saveProfile({
          nickname,
          avatarPath: this.data.avatarPath,
        });
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
