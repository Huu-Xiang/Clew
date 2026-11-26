import React from "react";

import { X } from "@phosphor-icons/react";
import { ChatGPTAccountPanel } from "./ChatGPTAccountPanel";
import { LanguageSelect } from "./LanguageSelect";
import { SectionHead } from "./SettingsSection";
import { SwitchRow } from "./ui/SwitchRow";
import type { ChatGPTAccountController } from "../hooks/useChatGPTAccount";
import { MEMORY_MODES, type SettingsDraftSetters, type SettingsDrafts } from "../lib/appContracts";
import type { LocalePreference } from "../lib/appLocale";
import type { AppCopy } from "../lib/appCopy";
import { DEFAULT_CANVAS_STYLE, type CanvasStylePreferences } from "../lib/canvasStyle";
import type { GraphEnvelope, SnapshotRecord, WorkspaceConfig, WorkspaceEnvelope } from "../lib/types";
import { useModalAccessibility } from "../lib/useModalAccessibility";

type StateSetter<T> = React.Dispatch<React.SetStateAction<T>>;
type SettingsModalProps = LocalePreference & {
  isSettingsOpen: boolean;
  copy: AppCopy;
  setSettingsOpen: StateSetter<boolean>;
  currentConfig: WorkspaceConfig | null;
  drafts: SettingsDrafts;
  setDrafts: SettingsDraftSetters;
  chatgpt: ChatGPTAccountController;
  activeGraph: GraphEnvelope | null;
  loadSnapshots: () => Promise<void>;
  historyLoading: boolean;
  historyError: string | null;
  snapshots: SnapshotRecord[];
  data: WorkspaceEnvelope | null;
  rollbackSnapshot: (snapshotId: number) => Promise<void>;
  configSaving: boolean;
  settingsDirty: boolean;
  saveSettings: () => void;
  addMaterialSource?: (path: string, label?: string) => Promise<void>;
  removeMaterialSource?: (sourceId: string) => Promise<void>;
  canvasStyle?: CanvasStylePreferences;
  setCanvasStyle?: React.Dispatch<React.SetStateAction<CanvasStylePreferences>>;
};

export function SettingsModal(props: SettingsModalProps): React.JSX.Element | null {
  const {
    isSettingsOpen,
    copy,
    setSettingsOpen,
    currentConfig,
    drafts,
    setDrafts,
    chatgpt,
    locale,
    changeLocale,
    activeGraph,
    loadSnapshots,
    historyLoading,
    historyError,
    snapshots,
    data,
    rollbackSnapshot,
    configSaving,
    settingsDirty,
    saveSettings,
    addMaterialSource,
    removeMaterialSource,
    canvasStyle,
    setCanvasStyle,
  } = props;
  const [materialPathDraft, setMaterialPathDraft] = React.useState("");
  const [materialLabelDraft, setMaterialLabelDraft] = React.useState("");
  const [materialBusy, setMaterialBusy] = React.useState(false);
  const [materialError, setMaterialError] = React.useState<string | null>(null);
  const {
    assistantNickname: assistantNicknameDraft,
    persona: personaDraft,
    disableIdleAnimations: disableIdleAnimationsDraft,
    memoryMode: memoryModeDraft,
    memoryHistoryLimit: memoryHistoryLimitDraft,
    memoryIncludeGraphContext: memoryIncludeGraphContextDraft,
    memoryIncludeProgressContext: memoryIncludeProgressContextDraft,
    memoryIncludeQuizContext: memoryIncludeQuizContextDraft,
    memoryIncludeFrontierContext: memoryIncludeFrontierContextDraft,
    memoryIncludeSelectedTopicContext: memoryIncludeSelectedTopicContextDraft,
    enableClosureTests: enableClosureTestsDraft,
    debugModeEnabled: debugModeEnabledDraft,
    straightEdgeLines: straightEdgeLinesDraft,
    quizQuestionCount: quizQuestionCountDraft,
    quizPassCount: quizPassCountDraft,
  } = drafts;
  const {
    assistantNickname: setAssistantNicknameDraft,
    persona: setPersonaDraft,
    disableIdleAnimations: setDisableIdleAnimationsDraft,
    memoryMode: setMemoryModeDraft,
    memoryHistoryLimit: setMemoryHistoryLimitDraft,
    memoryIncludeGraphContext: setMemoryIncludeGraphContextDraft,
    memoryIncludeProgressContext: setMemoryIncludeProgressContextDraft,
    memoryIncludeQuizContext: setMemoryIncludeQuizContextDraft,
    memoryIncludeFrontierContext: setMemoryIncludeFrontierContextDraft,
    memoryIncludeSelectedTopicContext: setMemoryIncludeSelectedTopicContextDraft,
    enableClosureTests: setEnableClosureTestsDraft,
    debugModeEnabled: setDebugModeEnabledDraft,
    straightEdgeLines: setStraightEdgeLinesDraft,
    quizQuestionCount: setQuizQuestionCountDraft,
    quizPassCount: setQuizPassCountDraft,
  } = setDrafts;
  const modalRef = React.useRef<HTMLDivElement | null>(null);
  const closeRef = React.useRef<HTMLButtonElement | null>(null);
  const close = React.useCallback(() => setSettingsOpen(false), [setSettingsOpen]);
  useModalAccessibility({ isOpen: isSettingsOpen, modalRef, onClose: close, initialFocusRef: closeRef });
  if (!isSettingsOpen) {
    return null;
  }

  const activeMemoryOption = copy.settingsPanel.memoryModes[memoryModeDraft];
  const activeMemoryValues = memoryModeDraft === "custom" ? copy.settingsPanel.customMemory(drafts) : activeMemoryOption.description;

  return (
    <div className="stOverlay">
      <div ref={modalRef} className="stModal" role="dialog" aria-modal="true" aria-label={copy.settings.workspaceConfiguration} tabIndex={-1}>
        <header className="stHeader">
          <h2>{copy.settings.workspaceConfiguration}</h2>
          <button ref={closeRef} className="uiIconButton" onClick={close} type="button" aria-label={copy.settingsPanel.closeSettings}>
            <X size={15} weight="bold" aria-hidden="true" />
          </button>
        </header>

        <div className="stScroll">
          <div className="stGrid">
            <div className="stColumn">
              <ChatGPTAccountPanel copy={copy} chatgpt={chatgpt} drafts={drafts} setDrafts={setDrafts} />

              <section className="stSection">
                <SectionHead eyebrow={copy.settingsPanel.preferences} title={copy.settingsPanel.assistantAndWorkspace} />
                <LanguageSelect locale={locale} changeLocale={changeLocale} copy={copy.locale} />
                <label className="uiField">
                  <span className="uiLabel">{copy.settingsPanel.assistantNickname}</span>
                  <input
                    className="uiInput"
                    value={assistantNicknameDraft}
                    onChange={(event) => setAssistantNicknameDraft(event.target.value)}
                    placeholder={copy.settingsPanel.assistantNicknamePlaceholder}
                    maxLength={80}
                  />
                  <span className="uiHelp">{copy.settingsPanel.assistantNicknameHelp}</span>
                </label>
                <label className="uiField">
                  <span className="uiLabel">{copy.settingsPanel.personaRules}</span>
                  <textarea
                    className="uiTextarea"
                    value={personaDraft}
                    onChange={(event) => setPersonaDraft(event.target.value)}
                    placeholder={copy.settingsPanel.personaPlaceholder}
                  />
                </label>
                <div className="uiRows">
                  <SwitchRow title={copy.settingsPanel.idleGraphMotion} help={copy.settingsPanel.idleGraphMotionHelp} checked={disableIdleAnimationsDraft} onChange={setDisableIdleAnimationsDraft} />
                  <SwitchRow title={copy.settingsPanel.debugMode} help={copy.settingsPanel.debugModeHelp} checked={debugModeEnabledDraft} onChange={setDebugModeEnabledDraft} />
                  <SwitchRow title={copy.settingsPanel.edgeLines} help={copy.settingsPanel.edgeLinesHelp} checked={straightEdgeLinesDraft} onChange={setStraightEdgeLinesDraft} />
                </div>
              </section>

              {canvasStyle && setCanvasStyle ? (
                <section className="stSection">
                  <SectionHead
                    eyebrow={copy.settingsPanel.canvasStyleEyebrow}
                    title={copy.settingsPanel.canvasStyleTitle}
                    action={(
                      <button
                        className="uiButton uiButtonQuiet uiButtonSmall"
                        onClick={() => setCanvasStyle({ ...DEFAULT_CANVAS_STYLE })}
                        type="button"
                      >
                        {copy.settingsPanel.canvasStyleReset}
                      </button>
                    )}
                  />
                  <div className="canvasStyleSliders">
                    <label className="canvasStyleSliderRow">
                      <span className="canvasStyleSliderHead">
                        <span className="uiLabel">{copy.settingsPanel.canvasFontSize}</span>
                        <span className="canvasStyleSliderVal">{canvasStyle.labelFontSize}px</span>
                      </span>
                      <input
                        className="canvasStyleRange"
                        type="range"
                        min={10}
                        max={18}
                        step={1}
                        value={canvasStyle.labelFontSize}
                        onChange={(event) => setCanvasStyle((current) => ({ ...current, labelFontSize: Number(event.target.value) }))}
                      />
                    </label>
                    <label className="canvasStyleSliderRow">
                      <span className="canvasStyleSliderHead">
                        <span className="uiLabel">{copy.settingsPanel.canvasLabelOpacity}</span>
                        <span className="canvasStyleSliderVal">{Math.round(canvasStyle.labelOpacity * 100)}%</span>
                      </span>
                      <input
                        className="canvasStyleRange"
                        type="range"
                        min={0.3}
                        max={1}
                        step={0.05}
                        value={canvasStyle.labelOpacity}
                        onChange={(event) => setCanvasStyle((current) => ({ ...current, labelOpacity: Number(event.target.value) }))}
                      />
                    </label>
                    <label className="canvasStyleSliderRow">
                      <span className="canvasStyleSliderHead">
                        <span className="uiLabel">{copy.settingsPanel.canvasEdgeOpacity}</span>
                        <span className="canvasStyleSliderVal">{Math.round(canvasStyle.edgeOpacity * 100)}%</span>
                      </span>
                      <input
                        className="canvasStyleRange"
                        type="range"
                        min={0.06}
                        max={0.65}
                        step={0.02}
                        value={canvasStyle.edgeOpacity}
                        onChange={(event) => setCanvasStyle((current) => ({ ...current, edgeOpacity: Number(event.target.value) }))}
                      />
                    </label>
                    <label className="canvasStyleSliderRow">
                      <span className="canvasStyleSliderHead">
                        <span className="uiLabel">{copy.settingsPanel.canvasEdgeWidth}</span>
                        <span className="canvasStyleSliderVal">{canvasStyle.edgeWidth.toFixed(1)}px</span>
                      </span>
                      <input
                        className="canvasStyleRange"
                        type="range"
                        min={0.8}
                        max={3}
                        step={0.2}
                        value={canvasStyle.edgeWidth}
                        onChange={(event) => setCanvasStyle((current) => ({ ...current, edgeWidth: Number(event.target.value) }))}
                      />
                    </label>
                  </div>
                  <div className="uiRows">
                    <SwitchRow
                      title={copy.settingsPanel.canvasZoneOutlines}
                      help={copy.settingsPanel.canvasZoneOutlinesHelp}
                      checked={canvasStyle.showZoneOutlines}
                      onChange={(checked) => setCanvasStyle((current) => ({ ...current, showZoneOutlines: checked }))}
                    />
                  </div>
                </section>
              ) : null}

              <section className="stSection">
                <SectionHead eyebrow={copy.settingsPanel.aiBehavior} title={copy.settingsPanel.memory} />
                <p className="stLead">{copy.settingsPanel.memoryLead}</p>
                <div className="uiSegmented">
                  {MEMORY_MODES.map((id) => (
                    <button
                      key={id}
                      className={memoryModeDraft === id ? "uiSegmentedActive" : undefined}
                      onClick={() => setMemoryModeDraft(id)}
                      type="button"
                      aria-pressed={memoryModeDraft === id}
                    >
                      <span>{copy.settingsPanel.memoryModes[id].label}</span>
                      <span>{copy.settingsPanel.memoryModes[id].title}</span>
                    </button>
                  ))}
                </div>
                <p className="uiHelp"><strong>{activeMemoryOption.label}</strong> · {activeMemoryValues}</p>
                {memoryModeDraft === "custom" ? (
                  <>
                    <label className="uiField">
                      <span className="uiLabel">{copy.settingsPanel.memoryHistoryLimit}</span>
                      <input
                        className="uiInput stNarrow"
                        type="number"
                        step={1}
                        value={memoryHistoryLimitDraft}
                        onChange={(event) => setMemoryHistoryLimitDraft(Number.isNaN(event.currentTarget.valueAsNumber) ? 0 : event.currentTarget.valueAsNumber)}
                      />
                    </label>
                    <div className="uiRows">
                      <SwitchRow title={copy.settingsPanel.memoryGraphContext} checked={memoryIncludeGraphContextDraft} onChange={setMemoryIncludeGraphContextDraft} />
                      <SwitchRow title={copy.settingsPanel.memoryProgressContext} checked={memoryIncludeProgressContextDraft} onChange={setMemoryIncludeProgressContextDraft} />
                      <SwitchRow title={copy.settingsPanel.memoryQuizContext} checked={memoryIncludeQuizContextDraft} onChange={setMemoryIncludeQuizContextDraft} />
                      <SwitchRow title={copy.settingsPanel.memoryFrontierContext} checked={memoryIncludeFrontierContextDraft} onChange={setMemoryIncludeFrontierContextDraft} />
                      <SwitchRow title={copy.settingsPanel.memorySelectedTopicContext} checked={memoryIncludeSelectedTopicContextDraft} onChange={setMemoryIncludeSelectedTopicContextDraft} />
                    </div>
                  </>
                ) : null}
              </section>
            </div>

            <div className="stColumn">
              {activeGraph && addMaterialSource && removeMaterialSource ? (
                <section className="stSection">
                  <SectionHead
                    eyebrow={copy.sessions.materialsSectionEyebrow}
                    title={copy.sessions.materialsSectionTitle}
                    action={window.clewDesktop?.pickMaterialFolder ? (
                      <button
                        className="uiButton uiButtonQuiet uiButtonSmall"
                        disabled={materialBusy}
                        onClick={() => {
                          void (async () => {
                            const picked = await window.clewDesktop?.pickMaterialFolder?.();
                            if (picked) {
                              setMaterialPathDraft(picked);
                              setMaterialError(null);
                            }
                          })();
                        }}
                        type="button"
                      >
                        {copy.sessions.materialsPickFolder}
                      </button>
                    ) : undefined}
                  />
                  <p className="stLead">{copy.sessions.materialsHelp}</p>
                  <label className="uiField">
                    <input
                      className="uiInput"
                      value={materialPathDraft}
                      onChange={(event) => setMaterialPathDraft(event.target.value)}
                      placeholder={copy.sessions.materialsPathPlaceholder}
                    />
                  </label>
                  <div className="stFieldPair">
                    <input
                      className="uiInput"
                      value={materialLabelDraft}
                      onChange={(event) => setMaterialLabelDraft(event.target.value)}
                      placeholder={copy.sessions.materialsLabelPlaceholder}
                    />
                    <button
                      className="uiButton uiButtonPrimary uiButtonSmall"
                      disabled={materialBusy || !materialPathDraft.trim()}
                      onClick={() => {
                        void (async () => {
                          setMaterialBusy(true);
                          setMaterialError(null);
                          try {
                            await addMaterialSource(materialPathDraft.trim(), materialLabelDraft.trim() || undefined);
                            setMaterialPathDraft("");
                            setMaterialLabelDraft("");
                          } catch (cause) {
                            setMaterialError(cause instanceof Error ? cause.message : copy.sessions.materialsAddFailed);
                          } finally {
                            setMaterialBusy(false);
                          }
                        })();
                      }}
                      type="button"
                    >
                      {materialBusy ? copy.sessions.materialsAdding : copy.sessions.materialsAdd}
                    </button>
                  </div>
                  {materialError ? <div className="inlineNotice inlineNoticeError">{materialError}</div> : null}
                  {(activeGraph.material_sources?.length ?? 0) > 0 ? (
                    <div className="stSnapshots">
                      {(activeGraph.material_sources ?? []).map((source) => (
                        <div key={source.id} className="stSnapshot">
                          <div className="stSnapshotMain">
                            <div className="stSnapshotTitle">{source.label}</div>
                            <div className="stSnapshotMeta"><span>{source.path}</span></div>
                          </div>
                          <button
                            className="uiButton uiButtonSmall"
                            disabled={materialBusy}
                            onClick={() => {
                              void (async () => {
                                setMaterialBusy(true);
                                setMaterialError(null);
                                try {
                                  await removeMaterialSource(source.id);
                                } catch (cause) {
                                  setMaterialError(cause instanceof Error ? cause.message : copy.sessions.materialsRemoveFailed);
                                } finally {
                                  setMaterialBusy(false);
                                }
                              })();
                            }}
                            type="button"
                          >
                            {copy.sessions.materialsRemove}
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="uiHelp">{copy.sessions.materialsEmpty}</p>
                  )}
                </section>
              ) : null}

              {activeGraph ? (
                <section className="stSection">
                  <SectionHead
                    eyebrow={copy.settingsPanel.history}
                    title={copy.settingsPanel.snapshots}
                    action={<button className="uiButton uiButtonQuiet uiButtonSmall" onClick={() => void loadSnapshots()} type="button">{historyLoading ? copy.settingsPanel.refreshing : copy.settingsPanel.refresh}</button>}
                  />
                  {historyError ? <div className="inlineNotice inlineNoticeError">{historyError}</div> : null}
                  {snapshots.length > 0 ? (
                    <div className="stSnapshots">
                      {snapshots.map((snapshot) => {
                        const current = data?.snapshot.id === snapshot.id;
                        const sources = copy.settingsPanel.snapshotSources;
                        const source = Object.hasOwn(sources, snapshot.source) ? sources[snapshot.source as keyof typeof sources] : snapshot.source;
                        return (
                          <div key={snapshot.id} className={`stSnapshot${current ? " stSnapshotCurrent" : ""}`}>
                            <div className="stSnapshotMain">
                              <div className="stSnapshotTitle">{copy.settingsPanel.snapshotLabel(snapshot.id)}</div>
                              <div className="stSnapshotMeta">
                                <span>{source}</span>
                                {snapshot.reason && snapshot.source !== "seed" ? <span>{snapshot.reason}</span> : null}
                              </div>
                            </div>
                            {current ? (
                              <span className="uiTag">{copy.settingsPanel.current}</span>
                            ) : (
                              <button className="uiButton uiButtonSmall" onClick={() => void rollbackSnapshot(snapshot.id)} type="button">
                                {copy.settingsPanel.rollback}
                              </button>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="uiHelp">{copy.settingsPanel.noSnapshots}</p>
                  )}
                </section>
              ) : null}

              <section className="stSection">
                <SectionHead eyebrow={copy.settingsPanel.closureQuiz} title={copy.settingsPanel.assessmentThreshold} />
                <div className="uiRows">
                  <SwitchRow title={copy.settingsPanel.enableClosureTests} help={copy.settingsPanel.enableClosureTestsHelp} checked={enableClosureTestsDraft} onChange={setEnableClosureTestsDraft} />
                </div>
                <div className="stFieldPair">
                  <label className="uiField">
                    <span className="uiLabel">{copy.settingsPanel.questionsPerQuiz}</span>
                    <select className="uiSelect" value={quizQuestionCountDraft} onChange={(event) => setQuizQuestionCountDraft(Number(event.target.value))}>
                      {Array.from({ length: 7 }, (_, index) => index + 6).map((value) => (
                        <option key={value} value={value}>{value}</option>
                      ))}
                    </select>
                  </label>
                  <label className="uiField">
                    <span className="uiLabel">{copy.settingsPanel.correctAnswersRequired}</span>
                    <select className="uiSelect" value={quizPassCountDraft} onChange={(event) => setQuizPassCountDraft(Math.min(Number(event.target.value), quizQuestionCountDraft))}>
                      {Array.from({ length: quizQuestionCountDraft }, (_, index) => index + 1).map((value) => (
                        <option key={value} value={value}>{value}</option>
                      ))}
                    </select>
                  </label>
                </div>
                <p className="uiHelp">{copy.settingsPanel.closureRule(quizPassCountDraft, quizQuestionCountDraft)}</p>
              </section>
            </div>
          </div>
        </div>

        <footer className="stFooter">
          <span className="uiHelp">{settingsDirty ? copy.settingsPanel.unsaved : copy.settingsPanel.saved}</span>
          <button className="uiButton uiButtonPrimary" disabled={configSaving || !currentConfig || !settingsDirty} onClick={saveSettings} type="button">
            {configSaving ? copy.settingsPanel.saving : copy.settingsPanel.save}
          </button>
        </footer>
      </div>
    </div>
  );
}
