const { attachmentLabel } = require('../../utils/chat-scenarios');

Component({
  properties: {
    message: {
      type: Object,
      value: {},
    },
  },

  data: {
    attachmentText: '',
    showCitations: false,
  },

  observers: {
    message(msg) {
      this.setData({
        attachmentText: msg && msg.attachment ? attachmentLabel(msg.attachment) : '',
        showCitations: false,
      });
    },
  },

  methods: {
    toggleCitations() {
      this.setData({ showCitations: !this.data.showCitations });
    },
  },
});
