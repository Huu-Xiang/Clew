import React, { useState } from "react";
import { Plus, X } from "@phosphor-icons/react";
import type { AppCopy } from "../lib/appCopy";
import type { MaterialSource, Topic } from "../lib/types";

export function TopicKeyFilesSection({
  copy,
  topic,
  materialSources,
  addTopicKeyFile,
  removeTopicKeyFile,
}: {
  copy: AppCopy;
  topic: Topic;
  materialSources: MaterialSource[];
  addTopicKeyFile: (topicId: string, sourceId: string, path: string, note?: string) => Promise<void>;
  removeTopicKeyFile: (topicId: string, keyFileId: string) => Promise<void>;
}): React.JSX.Element {
  const [adding, setAdding] = useState(false);
  const [sourceId, setSourceId] = useState(materialSources[0]?.id ?? "");
  const [pathDraft, setPathDraft] = useState("");
  const [noteDraft, setNoteDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const keyFiles = topic.key_files ?? [];
  const sourceLabelById = new Map(materialSources.map((source) => [source.id, source.label]));
  const effectiveSourceId = materialSources.some((source) => source.id === sourceId) ? sourceId : (materialSources[0]?.id ?? "");

  return (
    <div className="topicPopoverSection">
      <div className="topicPopoverSectionHeader">
        <div className="topicPopoverLabel">{copy.sessions.keyFilesLabel}</div>
        <button
          className="topicPopoverInlineAddButton"
          type="button"
          aria-label={copy.sessions.keyFilesAdd}
          title={copy.sessions.keyFilesAdd}
          onClick={() => {
            setAdding((current) => !current);
            setError(null);
          }}
        >
          <Plus size={12} weight="bold" aria-hidden="true" />
        </button>
      </div>
      {adding ? (
        <div className="topicKeyFileForm">
          {materialSources.length > 1 ? (
            <select className="uiSelect" value={effectiveSourceId} onChange={(event) => setSourceId(event.target.value)}>
              {materialSources.map((source) => (
                <option key={source.id} value={source.id}>{source.label}</option>
              ))}
            </select>
          ) : null}
          <input
            className="uiInput"
            value={pathDraft}
            onChange={(event) => setPathDraft(event.target.value)}
            placeholder={copy.sessions.keyFilesPathPlaceholder}
          />
          <input
            className="uiInput"
            value={noteDraft}
            onChange={(event) => setNoteDraft(event.target.value)}
            placeholder={copy.sessions.keyFilesNotePlaceholder}
          />
          {error ? <div className="inlineNotice inlineNoticeError">{error}</div> : null}
          <div className="topicKeyFileFormActions">
            <button
              className="uiButton uiButtonPrimary uiButtonSmall"
              disabled={busy || !effectiveSourceId || !pathDraft.trim()}
              onClick={() => {
                void (async () => {
                  setBusy(true);
                  setError(null);
                  try {
                    await addTopicKeyFile(topic.id, effectiveSourceId, pathDraft.trim(), noteDraft.trim());
                    setPathDraft("");
                    setNoteDraft("");
                    setAdding(false);
                  } catch (cause) {
                    setError(cause instanceof Error ? cause.message : copy.sessions.keyFilesAddFailed);
                  } finally {
                    setBusy(false);
                  }
                })();
              }}
              type="button"
            >
              {copy.sessions.keyFilesSave}
            </button>
          </div>
        </div>
      ) : null}
      {keyFiles.length > 0 ? (
        <div className="topicPopoverList">
          {keyFiles.map((item) => (
            <div key={item.id} className="topicKeyFileRow">
              <div className="topicKeyFileMeta">
                <div className="topicKeyFilePath">{item.path}</div>
                <div className="topicKeyFileSub">
                  <span>{sourceLabelById.get(item.source_id) ?? item.source_id}</span>
                  {item.note ? <span> · {item.note}</span> : null}
                </div>
              </div>
              <button
                className="topicKeyFileRemove"
                disabled={busy}
                aria-label={copy.sessions.keyFilesRemove}
                title={copy.sessions.keyFilesRemove}
                onClick={() => {
                  void (async () => {
                    setBusy(true);
                    setError(null);
                    try {
                      await removeTopicKeyFile(topic.id, item.id);
                    } catch (cause) {
                      setError(cause instanceof Error ? cause.message : copy.sessions.keyFilesRemoveFailed);
                    } finally {
                      setBusy(false);
                    }
                  })();
                }}
                type="button"
              >
                <X size={11} weight="bold" aria-hidden="true" />
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div className="topicPopoverEmpty">{copy.sessions.keyFilesEmpty}</div>
      )}
    </div>
  );
}
