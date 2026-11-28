import React from "react";
import { GithubLogo, Key, OpenAiLogo, XLogo } from "@phosphor-icons/react";
import type { ChatGPTAccountController } from "../hooks/useChatGPTAccount";
import { getAppCopy, type LocalePreference } from "../lib/appLocale";
import {
  DEFAULT_PROVIDER_PRESETS,
  parseModelInputList,
  saveCustomProvider,
  testProviderConnection,
} from "../lib/providers";
import { ClewLogo } from "./ClewLogo";
import { LanguageSelect } from "./LanguageSelect";

export function SignIn({ chatgpt, ...preference }: { chatgpt: ChatGPTAccountController } & LocalePreference) {
  const copy = getAppCopy(preference.locale);
  const { account, loading, error, warning, login, cancelLogin, logout, refresh } = chatgpt;
  const pending = account?.login;
  const completing = pending?.phase === "completing";
  const checking = !account && loading;

  const [showKeyForm, setShowKeyForm] = React.useState(false);
  const [presetId, setPresetId] = React.useState("anthropic");
  const [baseUrl, setBaseUrl] = React.useState(DEFAULT_PROVIDER_PRESETS[0].base_url);
  const [apiKey, setApiKey] = React.useState("");
  const [modelsText, setModelsText] = React.useState(DEFAULT_PROVIDER_PRESETS[0].default_models.join(", "));
  const [keyBusy, setKeyBusy] = React.useState(false);
  const [keyError, setKeyError] = React.useState<string | null>(null);

  const activePreset = DEFAULT_PROVIDER_PRESETS.find((p) => p.id === presetId) ?? DEFAULT_PROVIDER_PRESETS[0];

  function handlePresetChange(nextId: string) {
    setPresetId(nextId);
    const preset = DEFAULT_PROVIDER_PRESETS.find((p) => p.id === nextId);
    if (preset) {
      setBaseUrl(preset.base_url);
      setModelsText(preset.default_models.join(", "));
    }
    setKeyError(null);
  }

  async function handleCustomKeySubmit(event: React.FormEvent) {
    event.preventDefault();
    setKeyError(null);
    const manualModels = parseModelInputList(modelsText);
    setKeyBusy(true);
    try {
      const tested = await testProviderConnection({
        kind: activePreset.kind,
        base_url: baseUrl.trim() || undefined,
        api_key: apiKey.trim() || undefined,
        model: manualModels[0],
      });
      const resolvedModels = manualModels.length > 0 ? manualModels : tested.models.slice(0, 8);
      if (resolvedModels.length === 0) {
        throw new Error(copy.signIn.modelsPlaceholder);
      }
      await saveCustomProvider({
        name: activePreset.label,
        kind: activePreset.kind,
        base_url: baseUrl.trim() || undefined,
        api_key: apiKey.trim() || undefined,
        models: resolvedModels,
      });
      await refresh();
    } catch (cause) {
      setKeyError(cause instanceof Error ? cause.message : copy.signIn.loginFailed);
    } finally {
      setKeyBusy(false);
    }
  }

  return <main className="signIn">
    <section className="signInMain" aria-labelledby="signInTitle">
      <ClewLogo className="signInMark" />
      <h1 id="signInTitle">{copy.signIn.welcome}</h1>
      {!showKeyForm ? (
        <div className="signInAction">
          <button className="signInContinue" type="button" disabled={loading || completing} aria-busy={loading || completing}
            onClick={() => void login()}>
            <OpenAiLogo size={20} aria-hidden="true" />
            <span>{completing ? copy.signIn.finishing : pending ? copy.signIn.continueInBrowser : loading && !checking ? copy.signIn.opening : copy.signIn.continue}</span>
          </button>
          {pending && <div className="signInStatus" role="status">
            <p>{copy.signIn.finishInBrowser}</p>
            <button type="button" disabled={loading} onClick={() => void cancelLogin()}>{copy.dialogs.cancel}</button>
          </div>}
          <div className="signInDivider"><span>{copy.signIn.orUseApiKey}</span></div>
          <button className="signInSecondary" type="button" onClick={() => { setShowKeyForm(true); setKeyError(null); }}>
            <Key size={16} aria-hidden="true" />
            <span>{copy.signIn.useCustomApiKey}</span>
          </button>
        </div>
      ) : (
        <form className="signInKeyForm" onSubmit={(event) => void handleCustomKeySubmit(event)}>
          <label>
            <span>{copy.account.providerPreset}</span>
            <select value={presetId} onChange={(event) => handlePresetChange(event.target.value)} disabled={keyBusy}>
              {DEFAULT_PROVIDER_PRESETS.map((preset) => (
                <option key={preset.id} value={preset.id}>{preset.label}</option>
              ))}
            </select>
          </label>
          <label>
            <span>{copy.account.providerBaseUrl}</span>
            <input
              type="url"
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder={copy.signIn.baseUrlPlaceholder}
              disabled={keyBusy}
            />
          </label>
          <label>
            <span>{copy.account.providerApiKey}</span>
            <input
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder={copy.signIn.apiKeyPlaceholder}
              autoComplete="off"
              disabled={keyBusy}
            />
          </label>
          <label>
            <span>{copy.account.providerModels}</span>
            <input
              type="text"
              value={modelsText}
              onChange={(event) => setModelsText(event.target.value)}
              placeholder={copy.signIn.modelsPlaceholder}
              disabled={keyBusy}
            />
          </label>
          {keyError ? <div className="signInError" role="alert" style={{ marginTop: 4 }}>{keyError}</div> : null}
          <div className="signInKeyActions">
            <button className="signInSecondary" type="button" disabled={keyBusy} onClick={() => setShowKeyForm(false)}>
              {copy.signIn.backToSignIn}
            </button>
            <button className="signInContinue" type="submit" disabled={keyBusy}>
              {keyBusy ? copy.signIn.verifying : copy.signIn.verifyAndContinue}
            </button>
          </div>
        </form>
      )}
      {(error || account?.error) && !showKeyForm && <div className="signInError" role="alert">{error || account?.error}<button type="button" onClick={() => void refresh()}>{copy.launch.retry}</button></div>}
      {warning && <p className="signInStatus" role="status">{warning}</p>}
      {account && (account.can_disconnect || account.authenticated) && !account.sharing && <button className="signInQuiet" type="button" disabled={loading} onClick={() => void logout()}>{copy.signIn.disconnect}</button>}
      <footer className="signInFooter">
        <a href="https://github.com/miuuyy/Clew" target="_blank" rel="noopener noreferrer" aria-label={copy.signIn.star} title={copy.signIn.star}><GithubLogo size={20} aria-hidden="true" /></a>
        <a href="https://x.com/miu21590" target="_blank" rel="noopener noreferrer" aria-label={copy.signIn.follow} title={copy.signIn.follow}><XLogo size={18} aria-hidden="true" /></a>
        <a href={copy.locale.docsUrl} target="_blank" rel="noopener noreferrer">{copy.signIn.docs}</a>
        <LanguageSelect {...preference} copy={copy.locale} compact />
      </footer>
    </section>
  </main>;
}
