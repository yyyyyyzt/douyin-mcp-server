/** 读取用户在设置页选择的模型（本地缓存） */
const LLM_KEY = 'reno_llm_model';
const ASR_KEY = 'reno_asr_model';

function getSelectedModels() {
  return {
    llm_model: wx.getStorageSync(LLM_KEY) || '',
    asr_model: wx.getStorageSync(ASR_KEY) || '',
  };
}

module.exports = { getSelectedModels, LLM_KEY, ASR_KEY };
