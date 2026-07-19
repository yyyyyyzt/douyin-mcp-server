Component({
  data: {
    value: 'collect',
    list: [
      { value: 'collect', icon: 'upload', text: '收集', url: '/pages/collect/collect' },
      { value: 'knowledge', icon: 'book', text: '知识库', url: '/pages/knowledge/knowledge' },
      { value: 'chat', icon: 'chat', text: '问答', url: '/pages/chat/chat' },
    ],
  },
  methods: {
    onChange(e) {
      const value = e.detail.value;
      const item = this.data.list.find((i) => i.value === value);
      if (!item) return;
      this.setData({ value });
      wx.switchTab({ url: item.url });
    },
  },
});
