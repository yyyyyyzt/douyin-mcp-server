Component({
  data: {
    value: 'chat',
    list: [
      { value: 'collect', glyph: '＋', text: '收集', url: '/pages/collect/collect' },
      { value: 'chat', glyph: '◎', text: 'AI 助手', url: '/pages/chat/chat' },
      { value: 'knowledge', glyph: '☰', text: '知识库', url: '/pages/knowledge/knowledge' },
    ],
  },
  methods: {
    onTap(e) {
      const value = e.currentTarget.dataset.value;
      const item = this.data.list.find((i) => i.value === value);
      if (!item) return;
      this.setData({ value });
      wx.switchTab({ url: item.url });
    },
  },
});
