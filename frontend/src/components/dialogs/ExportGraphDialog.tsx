import React from "react";

import { Modal } from "../ui/Modal";
import { SwitchRow } from "../ui/SwitchRow";

import type { AppCopy } from "../../lib/appCopy";
import type {
  GraphEnvelope,
  GraphExportFormat,
  ObsidianExportOptions,
  StudyBookExportOptions,
  StudyBookMode,
} from "../../lib/types";

function patchObsidianExportOptions(
  setOptions: React.Dispatch<React.SetStateAction<ObsidianExportOptions>>,
  patch: Partial<ObsidianExportOptions>,
): void {
  setOptions((current) => ({ ...current, ...patch }));
}

function patchStudyBookOptions(
  setOptions: React.Dispatch<React.SetStateAction<StudyBookExportOptions>>,
  patch: Partial<StudyBookExportOptions>,
): void {
  setOptions((current) => ({ ...current, ...patch }));
}

export function ExportGraphDialog({
  target,
  modalRef,
  titleInputRef,
  closeModal,
  titleDraft,
  setTitleDraft,
  includeProgressDraft,
  setIncludeProgressDraft,
  formatDraft,
  setFormatDraft,
  obsidianOptionsDraft,
  setObsidianOptionsDraft,
  studyBookOptionsDraft,
  setStudyBookOptionsDraft,
  aiAuthenticated,
  error,
  loading,
  exportGraph,
  copy,
}: {
  target: GraphEnvelope | null;
  modalRef: React.RefObject<HTMLDivElement | null>;
  titleInputRef: React.RefObject<HTMLInputElement | null>;
  closeModal: () => void;
  titleDraft: string;
  setTitleDraft: React.Dispatch<React.SetStateAction<string>>;
  includeProgressDraft: boolean;
  setIncludeProgressDraft: React.Dispatch<React.SetStateAction<boolean>>;
  formatDraft: GraphExportFormat;
  setFormatDraft: React.Dispatch<React.SetStateAction<GraphExportFormat>>;
  obsidianOptionsDraft: ObsidianExportOptions;
  setObsidianOptionsDraft: React.Dispatch<React.SetStateAction<ObsidianExportOptions>>;
  studyBookOptionsDraft: StudyBookExportOptions;
  setStudyBookOptionsDraft: React.Dispatch<React.SetStateAction<StudyBookExportOptions>>;
  aiAuthenticated: boolean;
  error: string | null;
  loading: boolean;
  exportGraph: (graph: GraphEnvelope) => Promise<void>;
  copy: AppCopy;
}): React.JSX.Element | null {
  if (!target) return null;

  const obsidian = formatDraft === "mapmind_obsidian_export";
  const studyBook = formatDraft === "mapmind_study_book_html" || formatDraft === "mapmind_study_book_md";
  const toggleZone = (zoneId: string): void => {
    const current = studyBookOptionsDraft.zone_ids;
    const next = current.includes(zoneId)
      ? current.filter((id) => id !== zoneId)
      : [...current, zoneId];
    patchStudyBookOptions(setStudyBookOptionsDraft, { zone_ids: next });
  };

  return (
    <Modal
      id="export-graph-dialog"
      modalRef={modalRef}
      title={copy.dialogs.exportGraphTitle}
      description={copy.dialogs.exportGraphBody}
      closeLabel={copy.dialogs.cancel}
      onClose={closeModal}
      footer={<>
        <button className="uiButton uiButtonQuiet" onClick={closeModal} type="button">{copy.dialogs.cancel}</button>
        <button className="uiButton uiButtonPrimary" disabled={loading || !titleDraft.trim()} onClick={() => void exportGraph(target)} type="button">
          {loading ? copy.dialogs.exportingGraph : copy.dialogs.exportGraph}
        </button>
      </>}
    >
      <div className="uiFieldPair">
        <label className="uiField">
          <span className="uiLabel">{copy.dialogs.graphTitle}</span>
          <input ref={titleInputRef} className="uiInput" value={titleDraft} onChange={(event) => setTitleDraft(event.target.value)} placeholder={copy.dialogs.exportTitlePlaceholder} />
        </label>
        <label className="uiField">
          <span className="uiLabel">{copy.dialogs.exportFormat}</span>
          <select className="uiSelect" value={formatDraft} onChange={(event) => setFormatDraft(event.target.value as GraphExportFormat)}>
            <option value="mapmind_study_book_html">{copy.dialogs.exportFormatStudyBookHtml}</option>
            <option value="mapmind_study_book_md">{copy.dialogs.exportFormatStudyBookMd}</option>
            <option value="mapmind_graph_export">{copy.dialogs.exportFormatClew}</option>
            <option value="mapmind_obsidian_export">{copy.dialogs.exportFormatObsidian}</option>
          </select>
        </label>
      </div>
      {studyBook ? (
        <div className="uiField">
          <span className="uiLabel">{copy.dialogs.studyBookMode}</span>
          <select
            className="uiSelect"
            value={studyBookOptionsDraft.mode}
            onChange={(event) => patchStudyBookOptions(setStudyBookOptionsDraft, { mode: event.target.value as StudyBookMode })}
          >
            <option value="handbook">{copy.dialogs.studyBookModeHandbook}</option>
            <option value="blindspots_only">{copy.dialogs.studyBookModeBlindspots}</option>
          </select>
        </div>
      ) : null}
      {studyBook && target.zones.length > 0 ? (
        <div className="uiField">
          <span className="uiLabel">{copy.dialogs.studyBookZones}</span>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
            <button
              type="button"
              className={`uiButton ${studyBookOptionsDraft.zone_ids.length === 0 ? "uiButtonPrimary" : "uiButtonQuiet"}`}
              onClick={() => patchStudyBookOptions(setStudyBookOptionsDraft, { zone_ids: [] })}
            >
              {copy.dialogs.studyBookAllZones}
            </button>
            {target.zones.map((zone) => {
              const selected = studyBookOptionsDraft.zone_ids.includes(zone.id);
              return (
                <button
                  key={zone.id}
                  type="button"
                  className={`uiButton ${selected ? "uiButtonPrimary" : "uiButtonQuiet"}`}
                  onClick={() => toggleZone(zone.id)}
                >
                  {zone.title}
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
      <div className="uiRows">
        <SwitchRow title={copy.dialogs.includeOwnProgress} checked={includeProgressDraft} onChange={setIncludeProgressDraft} />
        {studyBook ? <>
          <SwitchRow
            title={copy.dialogs.studyBookIncludeNotes}
            checked={studyBookOptionsDraft.include_notes}
            onChange={(checked) => patchStudyBookOptions(setStudyBookOptionsDraft, { include_notes: checked })}
          />
          <SwitchRow
            title={copy.dialogs.studyBookIncludeMistakes}
            checked={studyBookOptionsDraft.include_mistakes}
            onChange={(checked) => patchStudyBookOptions(setStudyBookOptionsDraft, { include_mistakes: checked })}
          />
          <SwitchRow
            title={copy.dialogs.studyBookIncludeChatQa}
            checked={studyBookOptionsDraft.include_chat_qa}
            onChange={(checked) => patchStudyBookOptions(setStudyBookOptionsDraft, { include_chat_qa: checked })}
          />
          <SwitchRow
            title={copy.dialogs.studyBookAiSynthesize}
            help={aiAuthenticated ? copy.dialogs.studyBookAiSynthesizeHelp : copy.dialogs.studyBookAiRequiresAuth}
            checked={aiAuthenticated && studyBookOptionsDraft.ai_synthesize_blindspots}
            onChange={(checked) => {
              if (!aiAuthenticated) return;
              patchStudyBookOptions(setStudyBookOptionsDraft, { ai_synthesize_blindspots: checked });
            }}
          />
        </> : null}
        {obsidian ? <>
          <SwitchRow title={copy.dialogs.obsidianUseFoldersAsZones} help={copy.dialogs.obsidianUseFoldersAsZonesHelp} checked={obsidianOptionsDraft.use_folders_as_zones} onChange={(checked) => patchObsidianExportOptions(setObsidianOptionsDraft, { use_folders_as_zones: checked })} />
          <SwitchRow title={copy.dialogs.obsidianIncludeDescriptions} checked={obsidianOptionsDraft.include_descriptions} onChange={(checked) => patchObsidianExportOptions(setObsidianOptionsDraft, { include_descriptions: checked })} />
          <SwitchRow title={copy.dialogs.obsidianIncludeResources} checked={obsidianOptionsDraft.include_resources} onChange={(checked) => patchObsidianExportOptions(setObsidianOptionsDraft, { include_resources: checked })} />
          <SwitchRow title={copy.dialogs.obsidianIncludeArtifacts} checked={obsidianOptionsDraft.include_artifacts} onChange={(checked) => patchObsidianExportOptions(setObsidianOptionsDraft, { include_artifacts: checked })} />
        </> : null}
      </div>
      {studyBook ? <p className="uiHelp">{copy.dialogs.studyBookHint}</p> : null}
      {obsidian ? <p className="uiHelp">{copy.dialogs.obsidianExportHint}</p> : null}
      {error ? <div className="inlineNotice inlineNoticeError">{error}</div> : null}
    </Modal>
  );
}
