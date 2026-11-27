import React from "react";
import { createPortal } from "react-dom";
import { ArrowCounterClockwise, Check, Quotes } from "@phosphor-icons/react";

import type { GraphChatState } from "../../lib/appContracts";
import type { AppCopy } from "../../lib/appCopy";
import { renderDisplayText } from "../../lib/appUiHelpers";
import { normalizeQuotedText } from "../../lib/chatQuote";
import { summarizePreviewCounts, summarizeTopOperations } from "../../lib/graph";
import { AgentInteraction, type AgentControls } from "./AgentInteraction";
import { AssistantMarkdown } from "./AssistantMarkdown";
import { ClewLoader } from "../ClewLoader";
import { groupChatReplies, presentChatReply } from "../../lib/chatPresentation";

type AssistantMessage = GraphChatState["messages"][number];
type AssistantProposal = NonNullable<AssistantMessage["proposal"]>;

function AssistantProgress({ label }: { label: string }) {
  return <div className="assistantProgress" role="status" aria-label={label}>
    <span className="chatTypingDot" aria-hidden="true" />
    <span className="chatTypingDot" aria-hidden="true" />
    <span className="chatTypingDot" aria-hidden="true" />
  </div>;
}

export type AssistantThreadProps = {
  copy: AppCopy;
  agentControls: AgentControls;
  chatViewportRef: React.RefObject<HTMLDivElement | null>;
  chatThreadLoading: boolean;
  currentChatState: GraphChatState;
  visibleMessages: AssistantMessage[];
  chatLoading: boolean;
  hasInlinePlanningWidget: boolean;
  applyLoadingMessageId: string | null;
  applyProposalFromMessage: (messageId: string, proposal: AssistantProposal) => Promise<void>;
  updateCurrentChatState: (updater: (current: GraphChatState) => GraphChatState) => void;
  chatComposerRef: React.RefObject<HTMLTextAreaElement | null>;
};

export function AssistantThread({
  copy,
  agentControls,
  chatViewportRef,
  chatThreadLoading,
  currentChatState,
  visibleMessages,
  chatLoading,
  hasInlinePlanningWidget,
  applyLoadingMessageId,
  applyProposalFromMessage,
  updateCurrentChatState,
  chatComposerRef,
}: AssistantThreadProps): React.JSX.Element {
  const replies = groupChatReplies(visibleMessages);
  const activeReplyId = chatLoading && replies.some((reply) => reply.role === "assistant" && reply.id === currentChatState.runId)
    ? currentChatState.runId : null;
  const [selectionQuote, setSelectionQuote] = React.useState<{ text: string; top: number; left: number } | null>(null);

  React.useEffect(() => {
    const viewport = chatViewportRef.current;
    if (!viewport) return;
    const syncSelection = () => {
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed || selection.rangeCount === 0) {
        setSelectionQuote(null);
        return;
      }
      const text = normalizeQuotedText(selection.toString());
      if (!text) {
        setSelectionQuote(null);
        return;
      }
      const range = selection.getRangeAt(0);
      const toElement = (node: Node): Element | null => (node.nodeType === Node.ELEMENT_NODE ? (node as Element) : node.parentElement);
      const startEl = toElement(range.startContainer);
      const endEl = toElement(range.endContainer);
      if (!startEl || !endEl || !viewport.contains(startEl) || !viewport.contains(endEl)) {
        setSelectionQuote(null);
        return;
      }
      if (!startEl.closest(".chatMessage-assistant") || !endEl.closest(".chatMessage-assistant")) {
        setSelectionQuote(null);
        return;
      }
      const rect = range.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) {
        setSelectionQuote(null);
        return;
      }
      const left = Math.min(Math.max(rect.left + rect.width / 2, 72), window.innerWidth - 72);
      const top = Math.max(rect.top - 36, 12);
      setSelectionQuote({ text, top, left });
    };
    const clearSelectionQuote = () => setSelectionQuote(null);
    document.addEventListener("selectionchange", syncSelection);
    viewport.addEventListener("mouseup", syncSelection);
    viewport.addEventListener("keyup", syncSelection);
    viewport.addEventListener("scroll", clearSelectionQuote, { passive: true });
    return () => {
      document.removeEventListener("selectionchange", syncSelection);
      viewport.removeEventListener("mouseup", syncSelection);
      viewport.removeEventListener("keyup", syncSelection);
      viewport.removeEventListener("scroll", clearSelectionQuote);
    };
  }, [chatViewportRef]);

  // The thread unmounts when the chat window closes; reopening it starts at the latest message.
  React.useLayoutEffect(() => {
    const viewport = chatViewportRef.current;
    if (viewport) viewport.scrollTop = viewport.scrollHeight;
  }, [chatViewportRef]);
  const selectionPortal = selectionQuote && typeof document !== "undefined"
    ? createPortal(
      <button
        className="chatSelectionQuoteBtn"
        style={{ top: `${selectionQuote.top}px`, left: `${selectionQuote.left}px` }}
        onMouseDown={(event) => event.preventDefault()}
        onClick={() => {
          const picked = selectionQuote.text;
          updateCurrentChatState((current) => ({ ...current, quotedText: picked }));
          window.getSelection()?.removeAllRanges();
          setSelectionQuote(null);
          window.requestAnimationFrame(() => chatComposerRef.current?.focus());
        }}
        type="button"
      >
        <Quotes size={13} weight="bold" aria-hidden="true" />
        <span>{copy.sessions.quoteSelection}</span>
      </button>,
      document.body,
    )
    : null;
  return (
    <div ref={chatViewportRef} className="assistantThread">
      {selectionPortal}
      {chatThreadLoading ? (
        <div className="assistantHello assistantHelloLoading">
          <ClewLoader size={56} label={copy.sessions.loadingThread} />
        </div>
      ) : null}
      {currentChatState.messages.length === 0 && !chatThreadLoading ? (
        <div className="assistantHello">
          <div className="assistantHelloTitle">{copy.sessions.helloTitle}</div>
          <div className="assistantHelloCopy">{copy.sessions.helloCopy}</div>
        </div>
      ) : null}
      {replies.map((reply) => {
        const view = presentChatReply(reply, reply.id === activeReplyId, currentChatState.status === "waiting", copy.sessions);
        if (!view.texts.length && !view.cards.length && !view.commentary && !view.progress && !view.interrupted) return null;
        return <div key={reply.id} className={`chatMessage chatMessage-${reply.role}`}>
          <div className="chatBubble">
            {view.commentary ? <div className="chatCopy"><AssistantMarkdown content={view.commentary} /></div> : null}
            {view.texts.map((message) => <div key={message.id} className="chatCopy">
              {message.role === "assistant" ? <AssistantMarkdown content={message.content} /> : renderDisplayText(message.content)}
            </div>)}
            {reply.role === "user" && agentControls.revertMessage && reply.messages[0]?.id ? (
              <div className="chatUserActions">
                <button
                  className="chatRevertButton"
                  disabled={agentControls.revertLoadingMessageId === reply.messages[0].id}
                  onClick={() => void agentControls.revertMessage?.(reply.messages[0].id)}
                  title={copy.sessions.revertMessageTitle}
                  type="button"
                >
                  <ArrowCounterClockwise size={12} weight="bold" aria-hidden="true" />
                  <span>{copy.sessions.revertMessage}</span>
                </button>
              </div>
            ) : null}
            {view.cards.map((message) => {
              const proposal = message.proposal;
              const proposalCounts = proposal ? summarizePreviewCounts(proposal, copy) : [];
              const proposalHighlights = proposal ? summarizeTopOperations(proposal, copy) : [];
              const distillation = message.distillation;
              const distillProposal = distillation?.proposal ?? null;
              const distillCounts = distillProposal ? summarizePreviewCounts(distillProposal, copy) : [];
              const distillHighlights = distillProposal ? summarizeTopOperations(distillProposal, copy) : [];
              const distillSummaryApplied = Boolean(distillation?.summary?.applied);
              const distillProposalApplied = Boolean(distillation?.proposal_applied);
              const distillCanApplySummary = Boolean(distillation?.summary && !distillSummaryApplied);
              const distillCanApplyProposal = Boolean(distillProposal && !distillProposalApplied && distillProposal.apply_plan.validation.ok);
              return <React.Fragment key={message.id}>
                {message.activity?.status === "failed" && message.question?.status !== "interrupted" && message.inline_quiz?.status !== "interrupted"
                  ? <div className="inlineNotice inlineNoticeError">{copy.errors.request(copy.sessions.toolFailed, message.activity.detail)}</div> : null}
                {message.question || message.inline_quiz ? <AgentInteraction question={message.question} quiz={message.inline_quiz} controls={agentControls} copy={copy} /> : null}
                {distillation ? (
                  <div className="proposalInlineCard distillationCard">
                    <div className="proposalInlineHead">
                      <div>
                        <div className="proposalInlineTitle">{copy.sessions.distillationCardTitle}</div>
                        {distillProposal?.display.summary ? (
                          <div className="proposalInlineNote">{distillProposal.display.summary}</div>
                        ) : null}
                      </div>
                      {distillCanApplySummary && distillCanApplyProposal && agentControls.applyDistillationAll ? (
                        <button
                          className="proposalOpenButton"
                          disabled={agentControls.distillSummaryLoadingId === message.id || applyLoadingMessageId === message.id}
                          onClick={() => void agentControls.applyDistillationAll?.(message.id, distillation)}
                          type="button"
                        >
                          {copy.sessions.distillationApplyAll}
                        </button>
                      ) : null}
                    </div>
                    {distillation.summary ? (
                      <div className="distillationSection">
                        <div className="distillationSectionHead">
                          <div className="distillationSectionMeta">
                            <span className="distillationSectionLabel">{copy.sessions.distillationSummaryLabel}</span>
                            <strong className="distillationSummaryTitle">{distillation.summary.title}</strong>
                          </div>
                          {agentControls.applyDistillationSummary ? (
                            <button
                              className={`distillationActionButton${distillSummaryApplied ? " distillationActionButtonDone" : ""}`}
                              disabled={distillSummaryApplied || agentControls.distillSummaryLoadingId === message.id}
                              onClick={() => void agentControls.applyDistillationSummary?.(message.id)}
                              type="button"
                            >
                              {agentControls.distillSummaryLoadingId === message.id
                                ? "…"
                                : distillSummaryApplied
                                  ? <><Check size={12} weight="bold" aria-hidden="true" /><span>{copy.sessions.distillationSummarySaved}</span></>
                                  : copy.sessions.distillationSaveSummary}
                            </button>
                          ) : null}
                        </div>
                        <div className="distillationSummaryBody chatCopy">
                          <AssistantMarkdown content={distillation.summary.body} />
                        </div>
                      </div>
                    ) : null}
                    {distillProposal ? (
                      <div className="distillationSection">
                        <div className="distillationSectionHead">
                          <span className="distillationSectionLabel">{copy.sessions.distillationNodesLabel}</span>
                          <button
                            className={`distillationActionButton${distillProposalApplied ? " distillationActionButtonDone" : ""}`}
                            disabled={applyLoadingMessageId === message.id || distillProposalApplied || !distillProposal.apply_plan.validation.ok}
                            onClick={() => void (agentControls.applyDistillationProposal ?? applyProposalFromMessage)(message.id, distillProposal)}
                            type="button"
                          >
                            {applyLoadingMessageId === message.id
                              ? "…"
                              : distillProposalApplied
                                ? <><Check size={12} weight="bold" aria-hidden="true" /><span>{copy.sessions.applied}</span></>
                                : copy.sessions.distillationApplyNodes}
                          </button>
                        </div>
                        {distillCounts.length > 0 ? (
                          <div className="proposalStats">
                            {distillCounts.map((item) => (
                              <div key={item.label} className="proposalStat">
                                <strong>{item.value}</strong>
                                <span>{item.label}</span>
                              </div>
                            ))}
                          </div>
                        ) : null}
                        {distillHighlights.length > 0 ? (
                          <div className="proposalMiniList">
                            {distillHighlights.map((item, index) => (
                              <div key={`${item.label}-${item.target}-${index}`} className="proposalMiniItem">
                                <span>{item.target}</span>
                                <span className="proposalMiniAction">{item.label}</span>
                              </div>
                            ))}
                          </div>
                        ) : null}
                        <details className="proposalReviewDetails">
                          <summary>{copy.sessions.reviewChanges}</summary>
                          {distillProposal.proposal_envelope.operations.map((operation) => <div key={operation.op_id} className="proposalReviewItem">
                            {operation.topic ? <><strong>{operation.topic.title}</strong><AssistantMarkdown content={operation.topic.description} />
                              {operation.topic.estimated_minutes > 0 ? <div className="proposalReviewMeta">{copy.sessions.studyTime(operation.topic.estimated_minutes)}</div> : null}
                            </> : operation.zone ? <strong>{operation.zone.title}</strong> : operation.edge ? <div>{operation.edge.source_topic_id} → {operation.edge.target_topic_id}</div> : null}
                            {operation.rationale ? <div className="proposalReviewMeta">{operation.rationale}</div> : null}
                          </div>)}
                        </details>
                        {distillProposal.apply_plan.validation.errors.length > 0 ? (
                          <div className="proposalNotices">
                            {distillProposal.apply_plan.validation.errors.map((entry) => (
                              <div key={entry} className="proposalNotice proposalNoticeError">{entry}</div>
                            ))}
                          </div>
                        ) : null}
                        {distillProposal.apply_plan.validation.warnings.length > 0 ? (
                          <div className="proposalNotices">
                            {distillProposal.apply_plan.validation.warnings.map((entry) => (
                              <div key={entry} className="proposalNotice proposalNoticeWarn">{entry}</div>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    ) : (
                      <div className="distillationEmptyNodes">{copy.sessions.distillationNoNewNodes}</div>
                    )}
                  </div>
                ) : null}
                {message.closure_quiz ? <div className="proposalInlineCard">
                  <div className="proposalInlineHead">
                    <div>
                      <div className="proposalInlineTitle">{copy.sessions.completionReady}</div>
                      <div className="proposalInlineNote">{copy.sessions.questionCount(message.closure_quiz.question_count)}</div>
                    </div>
                    <button className="proposalOpenButton" type="button" onClick={() => agentControls.openQuiz(message.closure_quiz!)}>{copy.sessions.openTest}</button>
                  </div>
                </div> : null}
                {message.planning_status ? (
                  <AssistantProgress label={message.planning_status} />
                ) : null}
                {message.planning_error ? (
                  <div className="inlineNotice inlineNoticeError">{copy.errors.request(copy.sessions.planningFailed, message.planning_error)}</div>
                ) : null}
                {proposal ? (
                  <div className="proposalInlineCard">
                    <div className="proposalInlineHead">
                      <div>
                        <div className="proposalInlineTitle">{proposal.display.summary}</div>
                        {proposal.proposal_envelope.assistant_message ? (
                          <div className="proposalInlineNote">{proposal.proposal_envelope.assistant_message}</div>
                        ) : null}
                      </div>
                      <button
                        className={`proposalAddButton${message.proposal_applied ? " proposalAddButtonApplied" : ""}`}
                        disabled={
                          applyLoadingMessageId === message.id ||
                          message.proposal_applied ||
                          !proposal.apply_plan.validation.ok
                        }
                        onClick={() => void applyProposalFromMessage(message.id, proposal)}
                        type="button"
                        aria-label={message.proposal_applied ? copy.sessions.proposalApplied : copy.sessions.addProposalToGraph}
                        title={message.proposal_applied ? copy.sessions.applied : copy.sessions.addProposalToGraph}
                      >
                        {applyLoadingMessageId === message.id
                          ? "…"
                          : message.proposal_applied
                            ? <span className="proposalAppliedMark" aria-hidden="true"><Check size={12} weight="bold" /></span>
                            : "+"}
                      </button>
                    </div>
                    {proposalCounts.length > 0 ? (
                      <div className="proposalStats">
                        {proposalCounts.map((item) => (
                          <div key={item.label} className="proposalStat">
                            <strong>{item.value}</strong>
                            <span>{item.label}</span>
                          </div>
                        ))}
                      </div>
                    ) : null}
                    {proposalHighlights.length > 0 ? (
                      <div className="proposalMiniList">
                        {proposalHighlights.map((item, index) => (
                          <button
                            key={`${item.label}-${item.target}-${index}`}
                            className="proposalMiniItem"
                            type="button"
                            onClick={() => {
                              updateCurrentChatState((current) => ({
                                ...current,
                                input: copy.sessions.expandFromTopic(item.target),
                              }));
                              window.requestAnimationFrame(() => chatComposerRef.current?.focus());
                            }}
                          >
                            <span>{item.target}</span>
                            <span className="proposalMiniAction">{item.label}</span>
                          </button>
                        ))}
                      </div>
                    ) : null}
                    <details className="proposalReviewDetails">
                      <summary>{copy.sessions.reviewChanges}</summary>
                      {proposal.proposal_envelope.operations.map((operation) => <div key={operation.op_id} className="proposalReviewItem">
                        {operation.topic ? <><strong>{operation.topic.title}</strong><AssistantMarkdown content={operation.topic.description} />
                          {operation.topic.estimated_minutes > 0 ? <div className="proposalReviewMeta">{copy.sessions.studyTime(operation.topic.estimated_minutes)}</div> : null}
                          {operation.topic.resources.map((resource, index) => <a key={`${resource.url}-${index}`} href={resource.url} target="_blank" rel="noopener noreferrer">{resource.label}</a>)}
                        </> : operation.zone ? <strong>{operation.zone.title}</strong> : operation.edge ? <div>{operation.edge.source_topic_id} → {operation.edge.target_topic_id}</div> : null}
                        {operation.rationale ? <div className="proposalReviewMeta">{operation.rationale}</div> : null}
                      </div>)}
                    </details>
                    {proposal.apply_plan.validation.errors.length > 0 ? (
                      <div className="proposalNotices">
                        {proposal.apply_plan.validation.errors.map((entry) => (
                          <div key={entry} className="proposalNotice proposalNoticeError">
                            {entry}
                          </div>
                        ))}
                      </div>
                    ) : null}
                    {proposal.apply_plan.validation.warnings.length > 0 ? (
                      <div className="proposalNotices">
                        {proposal.apply_plan.validation.warnings.map((entry) => (
                          <div key={entry} className="proposalNotice proposalNoticeWarn">
                            {entry}
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </React.Fragment>;
            })}
            {view.progress ? <AssistantProgress label={view.progressLabel} /> : null}
            {view.interrupted ? <div className="chatStopped">{copy.sessions.stopped}</div> : null}
          </div>
        </div>;
      })}
      {chatLoading && currentChatState.status !== "waiting" && !activeReplyId && !hasInlinePlanningWidget ? (
        <div className="chatMessage chatMessage-assistant">
          <div className="chatBubble">
            <AssistantProgress label={copy.sessions.working} />
          </div>
        </div>
      ) : null}
    </div>
  );
}
