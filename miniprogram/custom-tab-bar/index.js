Component({
  data: {
    value: 'chat',
    list: [
      { value: 'collect', icon: 'upload', text: '收集', url: '/pages/collect/collect' },
      { value: 'chat', icon: 'chat', text: 'AI 助手', url: '/pages/chat/chat' },
      { value: 'knowledge', icon: 'book', text: '知识库', url: '/pages/knowledge/knowledge' },
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
