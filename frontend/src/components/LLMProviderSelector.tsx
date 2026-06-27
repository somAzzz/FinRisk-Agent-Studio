import type { LLMProvider, LLMRunConfig } from "../types";

interface Props {
  value: LLMRunConfig;
  onChange: (next: LLMRunConfig) => void;
}

const PROVIDERS: Array<{
  value: LLMProvider;
  label: string;
  baseUrl: string;
  model: string;
}> = [
  {
    value: "sglang",
    label: "Local SGLang",
    baseUrl: "http://localhost:30000/v1",
    model: "Qwen/Qwen3.5-35B-A3B",
  },
  {
    value: "vllm",
    label: "Local vLLM",
    baseUrl: "http://localhost:8000/v1",
    model: "Qwen/Qwen3.5-35B-A3B",
  },
  {
    value: "deepseek",
    label: "DeepSeek API",
    baseUrl: "https://api.deepseek.com",
    model: "deepseek-v4-flash",
  },
  {
    value: "openai",
    label: "OpenAI API",
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
  },
];

function defaultsFor(provider: LLMProvider) {
  return PROVIDERS.find((p) => p.value === provider) ?? PROVIDERS[0];
}

export function LLMProviderSelector({ value, onChange }: Props) {
  const selected = defaultsFor(value.provider);
  return (
    <fieldset className="llm-selector" data-testid="llm-selector">
      <legend>LLM provider</legend>
      <div className="row">
        <label htmlFor="llm-provider">Provider</label>
        <select
          id="llm-provider"
          data-testid="llm-provider-select"
          value={value.provider}
          onChange={(e) => {
            const provider = e.target.value as LLMProvider;
            const defaults = defaultsFor(provider);
            onChange({
              provider,
              base_url: defaults.baseUrl,
              model: defaults.model,
            });
          }}
        >
          {PROVIDERS.map((provider) => (
            <option key={provider.value} value={provider.value}>
              {provider.label}
            </option>
          ))}
        </select>
      </div>
      <div className="row">
        <label htmlFor="llm-base-url">Base URL</label>
        <input
          id="llm-base-url"
          data-testid="llm-base-url-input"
          value={value.base_url ?? selected.baseUrl}
          onChange={(e) =>
            onChange({ ...value, base_url: e.target.value || null })
          }
        />
      </div>
      <div className="row">
        <label htmlFor="llm-model">Model</label>
        <input
          id="llm-model"
          data-testid="llm-model-input"
          value={value.model ?? selected.model}
          onChange={(e) =>
            onChange({ ...value, model: e.target.value || null })
          }
        />
      </div>
    </fieldset>
  );
}
