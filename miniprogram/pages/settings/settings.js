const { request, getBaseUrl } = require('../../utils/request');

const LLM_KEY = 'reno_llm_model';
const ASR_KEY = 'reno_asr_model';

Page({
  data: {
    apiBase: '',
    serverOk: false,
    serverStatus: '检测中…',
    wechatConfigured: false,
    checking: false,
    llmModels: [],
    asrModels: [],
    llmModel: '',
    asrModel: '',
    defaultLlm: '',
    defaultAsr: '',
  },

  onShow() {
    this.setData({ apiBase: getBaseUrl() });
    this.loadConfig();
  },

  async loadConfig() {
    this.setData({ checking: true, serverStatus: '检测中…' });
    try {
      const d = await request({ url: '/api/config', needAuth: false });
      const llmModels = d.llm_models || [];
      const asrModels = d.asr_models || [];
      const defaultLlm = (d.defaults && d.defaults.llm_model) || '';
      const defaultAsr = (d.defaults && d.defaults.asr_model) || '';
      const savedLlm = wx.getStorageSync(LLM_KEY) || '';
      const savedAsr = wx.getStorageSync(ASR_KEY) || '';
      this.setData({
        llmModels,
        asrModels,
        defaultLlm,
        defaultAsr,
        llmModel: savedLlm || defaultLlm,
        asrModel: savedAsr || defaultAsr,
        serverOk: !!d.api_key_configured,
        wechatConfigured: !!d.wechat_configured,
        serverStatus: d.wechat_configured
          ? (d.api_key_configured ? '已连接' : '微信已配置，ASR/LLM 密钥未配')
          : '服务端未配置微信登录 (WECHAT_APPID/SECRET)',
      });
    } catch (e) {
      this.setData({
        serverOk: false,
        serverStatus: e.message || '无法连接服务',
      });
    } finally {
      this.setData({ checking: false });
    }
  },

  refreshStatus() {
    this.loadConfig();
  },

  onLlmChange(e) {
    const llmModel = e.detail.value;
    this.setData({ llmModel });
    wx.setStorageSync(LLM_KEY, llmModel);
    wx.showToast({ title: '已切换对话模型', icon: 'none' });
  },

  onAsrChange(e) {
    const asrModel = e.detail.value;
    this.setData({ asrModel });
    wx.setStorageSync(ASR_KEY, asrModel);
    wx.showToast({ title: '已切换语音模型', icon: 'none' });
  },

  resetModels() {
    wx.removeStorageSync(LLM_KEY);
    wx.removeStorageSync(ASR_KEY);
    this.setData({
      llmModel: this.data.defaultLlm,
      asrModel: this.data.defaultAsr,
    });
    wx.showToast({ title: '已恢复默认', icon: 'success' });
  },
});
