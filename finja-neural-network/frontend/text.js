/*
  YourAI Text Utilities
  ====================
  Frontend module for the YourAI dashboard.

  Main Responsibilities:
  - Provide text formatting and sanitization helpers.
  - Normalize message text for rendering.
  - Share small string utilities across frontend modules.

  Side Effects:
  - Returns formatted strings for DOM rendering.
*/
const YourAIText = (() => {
  const FRIENDLY_MODELS = [
    [/^gemma-4/i, 'Gemma 4'],
    [/^gemma-3/i, 'Gemma 3'],
    [/^gemini-3/i, 'Gemini 3'],
    [/^gemini-2\.5-flash/i, 'Gemini 2.5 Flash'],
    [/^gemini-2\.5-pro/i, 'Gemini 2.5 Pro'],
    [/^gemini-2/i, 'Gemini 2'],
    [/^qwen3\.5/i, 'Qwen 3.5'],
    [/^qwen3-235b/i, 'Qwen 3 235B'],
    [/^qwen3/i, 'Qwen 3'],
    [/^kimi-k2/i, 'Kimi K2'],
    [/^gpt-oss/i, 'GPT-OSS'],
    [/^gpt-4/i, 'GPT-4'],
    [/^claude/i, 'Claude'],
    [/^nemotron/i, 'Nemotron'],
    [/^olmo/i, 'OLMo'],
    [/^rnj-1/i, 'RNJ-1'],
    [/^llama/i, 'Llama'],
    [/^mistral/i, 'Mistral'],
    [/^deepseek/i, 'DeepSeek'],
    [/^flux/i, 'Flux'],
    [/^gemma3n/i, 'Gemma 3n'],
  ];

  function cleanForSpeech(text) {
    return (text || '')
      .replace(/```[\s\S]*?```/g, '')
      .replace(/`[^`]+`/g, '')
      .replace(/\*\*([^*\n]+)\*\*/g, '$1')
      .replace(/\*[^*\n]+\*/g, '')
      .replace(/#{1,6}\s*/g, '')
      .replace(/!\[[^\]]*\]\([^)]+\)/g, '')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .replace(/[>|\-*+]{1,2}\s/g, '')
      .replace(/\n+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function friendlyModelName(modelId) {
    if (!modelId) return null;
    const raw = String(modelId);
    let name = raw.includes('/') ? raw.split('/').pop() : raw;
    for (const [re, friendly] of FRIENDLY_MODELS) {
      if (re.test(name)) return friendly;
    }
    return name
      .replace(/-instruct$/i, '')
      .replace(/-it$/i, '')
      .replace(/-preview$/i, '')
      .replace(/-\d+b(-a\d+b)?/gi, '')
      .replace(/[-_]+$/, '')
      .trim() || name;
  }

  return { cleanForSpeech, friendlyModelName };
})();
