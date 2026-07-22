const user = require('../../utils/user');

Component({
  properties: {
    showLogout: { type: Boolean, value: true },
  },
  data: {
    displayName: '',
    avatarUrl: '',
    avatarInitial: '友',
  },
  lifetimes: {
    attached() {
      user.syncComponentUser(this);
    },
  },
  pageLifetimes: {
    show() {
      user.syncComponentUser(this);
    },
  },
  methods: {
    onLogout() {
      wx.showModal({
        title: '退出登录',
        content: '退出后需要重新登录才能使用',
        confirmText: '退出',
        confirmColor: '#dc2626',
        success: (res) => {
          if (!res.confirm) return;
          user.logout();
          this.triggerEvent('logout');
        },
      });
    },
  },
});
