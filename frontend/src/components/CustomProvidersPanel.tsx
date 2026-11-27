import React from "react";

import type { ChatGPTAccountController } from "../hooks/useChatGPTAccount";
import type { AppCopy } from "../lib/appCopy";
import {
  DEFAULT_PROVIDER_PRESETS,
  deleteCustomProvider,
  deleteWebSearchConfig,
  parseModelInputList,
  saveCustomProvider,
  saveWebSearchConfig,
  testProviderConnection,
} from "../lib/providers";
import type { WebSearchKind } from "../lib/types";
import { SectionHead } from "./SettingsSection";

export function CustomProvidersPanel({
  copy,
  chatgpt,
}: {
  copy: AppCopy;
  chatgpt: ChatGPTAccountController;
}): React.JSX.Element {
  const labels = copy.account;
  const profiles = chatgpt.account?.custom_providers ?? [];
  const webSearch = chatgpt.account?.web_search_config ?? null;

  const [adding, setAdding] = React.useState(false);
  const [presetId, setPresetId] = React.useState("anthropic");
  const [name, setName] = React.useState(DEFAULT_PROVIDER_PRESETS[0].label);
  const [baseUrl, setBaseUrl] = React.useState(DEFAULT_PROVIDER_PRESETS[0].base_url);
  const [apiKey, setApiKey] = React.useState("");
  const [modelsText, setModelsText] = React.useState(DEFAULT_PROVIDER_PRESETS[0].default_models.join(", "));
  const [busy, setBusy] = React.useState(false);
  const [testing, setTesting] = React.useState(false);
  const [statusMessage, setStatusMessage] = React.useState<string | null>(null);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  const [wsProvider, setWsProvider] = React.useState<WebSearchKind>(webSearch?.provider ?? "tavily");
  const [wsKey, setWsKey] = React.useState("");
  const [wsBusy, setWsBusy] = React.useState(false);
  const [wsError, setWsError] = React.useState<string | null>(null);

  const activePreset = DEFAULT_PROVIDER_PRESETS.find((p) => p.id === presetId) ?? DEFAULT_PROVIDER_PRESETS[0];

  function selectPreset(nextId: string) {
    setPresetId(nextId);
    const preset = DEFAULT_PROVIDER_PRESETS.find((p) => p.id === nextId);
    if (preset) {
      setName(preset.label);
      setBaseUrl(preset.base_url);
      setModelsText(preset.default_models.join(", "));
    }
    setStatusMessage(null);
    setErrorMessage(null);
  }

  async function handleTest() {
    setErrorMessage(null);
    setStatusMessage(null);
    setTesting(true);
    try {
      const manual = parseModelInputList(modelsText);
      const res = await testProviderConnection({
        kind: activePreset.kind,
        base_url: baseUrl.trim() || undefined,
        api_key: apiKey.trim() || undefined,
        model: manual[0],
      });
      if (res.models.length > 0 && manual.length === 0) {
        setModelsText(res.models.slice(0, 8).join(", "));
      }
      setStatusMessage(labels.connectionTested(res.models.length));
    } catch (cause) {
      setErrorMessage(cause instanceof Error ? cause.message : copy.signIn.loginFailed);
    } finally {
      setTesting(false);
    }
  }

  async function handleSaveProvider() {
    setErrorMessage(null);
    setStatusMessage(null);
    const models = parseModelInputList(modelsText);
    if (!name.trim() || models.length === 0) {
      setErrorMessage(copy.signIn.modelsPlaceholder);
      return;
    }
    setBusy(true);
    try {
      await saveCustomProvider({
        name: name.trim(),
        kind: activePreset.kind,
        base_url: baseUrl.trim() || undefined,
        api_key: apiKey.trim() || undefined,
        models,
      });
      setApiKey("");
      setAdding(false);
      await chatgpt.refresh();
    } catch (cause) {
      setErrorMessage(cause instanceof Error ? cause.message : copy.signIn.loginFailed);
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteProvider(profileId: string) {
    setErrorMessage(null);
    setBusy(true);
    try {
      await deleteCustomProvider(profileId);
      await chatgpt.refresh();
    } catch (cause) {
      setErrorMessage(cause instanceof Error ? cause.message : copy.signIn.logoutFailed);
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveWebSearch() {
    setWsError(null);
    if (!wsKey.trim() && !webSearch?.has_key) return;
    setWsBusy(true);
    try {
      await saveWebSearchConfig({
        provider: wsProvider,
        api_key: wsKey.trim() || undefined,
        enabled: true,
      });
      setWsKey("");
      await chatgpt.refresh();
    } catch (cause) {
      setWsError(cause instanceof Error ? cause.message : copy.signIn.loginFailed);
    } finally {
      setWsBusy(false);
    }
  }

  async function handleRemoveWebSearch() {
    setWsError(null);
    setWsBusy(true);
    try {
      await deleteWebSearchConfig();
      await chatgpt.refresh();
    } catch (cause) {
      setWsError(cause instanceof Error ? cause.message : copy.signIn.logoutFailed);
    } finally {
      setWsBusy(false);
    }
  }

  return (
    <section className="stSection">
      <SectionHead
        eyebrow={labels.customProvidersEyebrow}
        title={labels.customProvidersTitle}
        action={
          !adding ? (
            <button
              className="uiButton uiButtonQuiet uiButtonSmall"
              type="button"
              onClick={() => {
                setAdding(true);
                setErrorMessage(null);
                setStatusMessage(null);
              }}
            >
              {labels.addProvider}
            </button>
          ) : null
        }
      />
      <p className="uiHelp">{labels.customProvidersHelp}</p>

      {profiles.length > 0 ? (
        <div className="stProviderList">
          {profiles.map((profile) => (
            <div key={profile.id} className="stProviderRow">
              <div className="stProviderMeta">
                <div className="stProviderTitleRow">
                  <span className="stAccountName">{profile.name}</span>
                  <span className={`stProviderBadge ${profile.supports_native_web_search ? "stProviderBadgeGood" : ""}`}>
                    {profile.supports_native_web_search ? labels.nativeWebSearchBadge : labels.noNativeWebSearchBadge}
                  </span>
                </div>
                <div className="uiHelp">
                  {profile.key_hint ? `${profile.key_hint} · ` : ""}
                  {profile.models.join(", ")}
                </div>
              </div>
              <button
                className="uiButton uiButtonQuiet uiButtonSmall"
                type="button"
                disabled={busy}
                onClick={() => void handleDeleteProvider(profile.id)}
              >
                {labels.removeProvider}
              </button>
            </div>
          ))}
        </div>
      ) : !adding ? (
        <p className="uiHelp">{labels.noCustomProviders}</p>
      ) : null}

      {adding ? (
        <div className="stProviderForm">
          <div className="stFieldPair">
            <label className="uiField">
              <span className="uiLabel">{labels.providerPreset}</span>
              <select className="uiSelect" value={presetId} onChange={(e) => selectPreset(e.target.value)} disabled={busy || testing}>
                {DEFAULT_PROVIDER_PRESETS.map((preset) => (
                  <option key={preset.id} value={preset.id}>{preset.label}</option>
                ))}
              </select>
            </label>
            <label className="uiField">
              <span className="uiLabel">{labels.providerName}</span>
              <input className="uiInput" value={name} onChange={(e) => setName(e.target.value)} disabled={busy || testing} />
            </label>
          </div>
          <label className="uiField">
            <span className="uiLabel">{labels.providerBaseUrl}</span>
            <input className="uiInput" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder={copy.signIn.baseUrlPlaceholder} disabled={busy || testing} />
          </label>
          <label className="uiField">
            <span className="uiLabel">{labels.providerApiKey}</span>
            <input
              className="uiInput"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={copy.signIn.apiKeyPlaceholder}
              autoComplete="off"
              disabled={busy || testing}
            />
          </label>
          <label className="uiField">
            <span className="uiLabel">{labels.providerModels}</span>
            <input className="uiInput" value={modelsText} onChange={(e) => setModelsText(e.target.value)} placeholder={copy.signIn.modelsPlaceholder} disabled={busy || testing} />
          </label>
          {statusMessage ? <div className="inlineNotice" role="status">{statusMessage}</div> : null}
          {errorMessage ? <div className="inlineNotice inlineNoticeError" role="alert">{errorMessage}</div> : null}
          <div className="stProviderActions">
            <button className="uiButton uiButtonSmall" type="button" disabled={busy || testing} onClick={() => void handleTest()}>
              {testing ? labels.testingConnection : labels.testConnection}
            </button>
            <button className="uiButton uiButtonPrimary uiButtonSmall" type="button" disabled={busy || testing} onClick={() => void handleSaveProvider()}>
              {busy ? labels.savingProvider : labels.saveProvider}
            </button>
            <button className="uiButton uiButtonQuiet uiButtonSmall" type="button" disabled={busy || testing} onClick={() => setAdding(false)}>
              {copy.dialogs.cancel}
            </button>
          </div>
        </div>
      ) : errorMessage ? (
        <div className="inlineNotice inlineNoticeError" role="alert">{errorMessage}</div>
      ) : null}

      <div className="stWebSearchBlock">
        <SectionHead eyebrow={labels.webSearchEyebrow} title={labels.webSearchTitle} />
        <p className="uiHelp">{labels.webSearchHelp}</p>
        {webSearch?.enabled ? (
          <div className="stProviderRow">
            <div className="stProviderMeta">
              <div className="stAccountName">{labels.webSearchActive(webSearch.provider, webSearch.key_hint)}</div>
            </div>
            <button className="uiButton uiButtonQuiet uiButtonSmall" type="button" disabled={wsBusy} onClick={() => void handleRemoveWebSearch()}>
              {labels.removeWebSearch}
            </button>
          </div>
        ) : null}
        <div className="stFieldPair">
          <label className="uiField">
            <span className="uiLabel">{labels.webSearchProvider}</span>
            <select className="uiSelect" value={wsProvider} onChange={(e) => setWsProvider(e.target.value as WebSearchKind)} disabled={wsBusy}>
              <option value="tavily">Tavily</option>
              <option value="brave">Brave Search</option>
            </select>
          </label>
          <label className="uiField">
            <span className="uiLabel">{labels.webSearchApiKey}</span>
            <input
              className="uiInput"
              type="password"
              value={wsKey}
              onChange={(e) => setWsKey(e.target.value)}
              placeholder="tvly-... / BSA..."
              autoComplete="off"
              disabled={wsBusy}
            />
          </label>
        </div>
        {wsError ? <div className="inlineNotice inlineNoticeError" role="alert">{wsError}</div> : null}
        <div className="stProviderActions">
          <button
            className="uiButton uiButtonSmall"
            type="button"
            disabled={wsBusy || (!wsKey.trim() && !webSearch?.has_key)}
            onClick={() => void handleSaveWebSearch()}
          >
            {labels.saveWebSearch}
          </button>
        </div>
      </div>
    </section>
  );
}
