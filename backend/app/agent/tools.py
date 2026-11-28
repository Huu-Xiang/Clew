from __future__ import annotations

import json
from typing import TYPE_CHECKING

from app.agent.context import graph_context
from app.agent.contracts import (
    BLINDSPOT_SYNTHESIS_TOOLS,
    CLOSURE_QUIZ_TOOLS,
    MATERIAL_TOOLS,
    TOOL_MODELS,
    ClosureQuizDraft,
    DistillationDraft,
    InlineQuizDraft,
    ListMaterialsDraft,
    ProposalDraft,
    QuestionDraft,
    ReadMaterialDraft,
    SearchMaterialsDraft,
    StudyBookSynthesisDraft,
    WebSearchDraft,
)
from app.agent.providers import execute_external_web_search
from app.models.domain import AgentActivity, AgentQuestion, ChatMessage, DistillationCard, DistillationSummary, InlineChatQuiz, QuizQuestion, TopicQuizSessionPublic
from app.services.material_service import MaterialService
from app.services.proposal_service import ProposalService
from app.services.quiz_service import QuizService

if TYPE_CHECKING:
    from app.agent.runtime import AgentRun, AgentRuntime


LABELS = {
    "read_graph": "Reading your graph",
    "read_topic": "Reading the topic",
    "list_materials": "Listing local materials",
    "search_materials": "Searching local materials",
    "read_material": "Reading local material",
    "web_search": "Searching the web",
    "propose_ingest": "Preparing a graph proposal",
    "propose_expand": "Preparing a graph proposal",
    "propose_distillation": "Distilling this conversation",
    "ask_question": "Waiting for your answer",
    "present_quiz": "Waiting for your answer",
    "create_closure_quiz": "Preparing your test",
    "submit_blindspot_synthesis": "Synthesizing personal blindspots",
}


def public_quiz(session) -> TopicQuizSessionPublic:
    return TopicQuizSessionPublic.model_validate(session.model_dump(mode="json"))


async def execute_tool(runtime: AgentRuntime, run: AgentRun, tool: str, call_id: str, raw_arguments: str) -> str:
    """Run one Clew tool call and return its function_call_output text. Results are
    idempotent per call id, so a replayed call never repeats a side effect."""
    canonical = json.dumps({"tool": tool, "arguments": raw_arguments}, sort_keys=True, ensure_ascii=False)
    cached = runtime.store.tool_result(call_id, run.thread_key, canonical)
    if cached is not None:
        return cached["output"]
    message = ChatMessage(id=f"tool-{call_id}", role="assistant", content="", model=run.model,
                          activity=AgentActivity(id=call_id, tool=tool, status="running", detail=LABELS.get(tool, tool)))
    try:
        if tool not in LABELS:
            raise ValueError("Unknown Clew tool.")
        if run.quiz_topic_id and tool not in (CLOSURE_QUIZ_TOOLS | MATERIAL_TOOLS):
            raise ValueError("This turn can only prepare the requested completion test.")
        try:
            arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"Tool arguments are not valid JSON: {exc}") from exc
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be a JSON object.")
        parsed = TOOL_MODELS[tool].model_validate(arguments) if tool in TOOL_MODELS else None
        runtime.publish_message(run, message)
        graph = runtime.repository.graph(run.graph_id)
        if tool == "read_graph":
            if arguments:
                raise ValueError("read_graph takes no arguments.")
            result = graph_context(graph)
        elif tool == "read_topic":
            if set(arguments) != {"topic_id"}:
                raise ValueError("read_topic requires only topic_id.")
            topic = next((t for t in graph.topics if t.id == arguments["topic_id"]), None)
            if topic is None:
                raise ValueError("Topic not found in this conversation's graph.")
            result = {"graph_version": graph.version, "topic": topic.model_dump(mode="json"),
                      "closure": QuizService(runtime.settings).build_closure_status(graph, topic.id).model_dump(mode="json")}
        elif tool == "list_materials":
            assert isinstance(parsed, ListMaterialsDraft)
            result = MaterialService().list_files(graph, source_id=parsed.source_id, subpath=parsed.subpath, max_depth=parsed.max_depth)
        elif tool == "search_materials":
            assert isinstance(parsed, SearchMaterialsDraft)
            result = MaterialService().search_text(graph, parsed.query, source_id=parsed.source_id, subpath=parsed.subpath)
        elif tool == "read_material":
            assert isinstance(parsed, ReadMaterialDraft)
            result = MaterialService().read_slice(graph, source_id=parsed.source_id, path=parsed.path, start=parsed.start, end=parsed.end)
        elif tool == "web_search":
            assert isinstance(parsed, WebSearchDraft)
            ws_cfg = runtime.providers.get_web_search()
            ws_key = runtime.providers.get_web_search_api_key()
            if not ws_cfg or not ws_cfg.enabled or not ws_key:
                raise ValueError("Custom web search is not configured in Settings.")
            run.web_searched = True
            result = await execute_external_web_search(
                provider=ws_cfg.provider,
                api_key=ws_key,
                query=parsed.query,
                max_results=parsed.max_results,
                http=runtime.provider_http,
            )
        elif tool in {"propose_ingest", "propose_expand"}:
            assert isinstance(parsed, ProposalDraft)
            proposal = ProposalService().prepare(graph, parsed, tool=tool, proposal_id=f"prop-{call_id}",
                prompt=run.request.prompt, model=run.model, use_grounding=run.web_searched)
            message.proposal = proposal
            message.action = tool
            result = {"status": "awaiting_review", "proposal_id": proposal.proposal_envelope.proposal_id,
                      "base_graph_version": graph.version, "preview": proposal.apply_plan.preview.model_dump(),
                      "message": "The proposal is ready in Clew. The user must accept it before the graph changes."}
        elif tool == "propose_distillation":
            assert isinstance(parsed, DistillationDraft)
            summary_card = None
            if parsed.summary is not None:
                target_topic_id = parsed.summary.topic_id or run.request.selected_topic_id
                if not target_topic_id or not any(t.id == target_topic_id for t in graph.topics):
                    raise ValueError("Distillation summary requires a valid topic_id in this graph.")
                summary_card = DistillationSummary(
                    topic_id=target_topic_id,
                    title=parsed.summary.title,
                    body=parsed.summary.body,
                )
            proposal = None
            if parsed.proposal is not None:
                proposal = ProposalService().prepare(
                    graph, parsed.proposal, tool="propose_expand", proposal_id=f"prop-{call_id}",
                    prompt=run.request.prompt, model=run.model, use_grounding=run.web_searched,
                )
            message.distillation = DistillationCard(
                distillation_id=f"distill-{call_id}",
                summary=summary_card,
                proposal=proposal,
            )
            message.action = "propose_distillation"
            result = {
                "status": "awaiting_review",
                "distillation_id": message.distillation.distillation_id,
                "has_summary": summary_card is not None,
                "has_proposal": proposal is not None,
                "base_graph_version": graph.version,
                "preview": proposal.apply_plan.preview.model_dump() if proposal else None,
                "message": "The distillation card is ready in Clew. The user chooses whether to save the summary and/or apply the graph proposal.",
            }
        elif tool in {"ask_question", "present_quiz"}:
            interaction_id = f"question-{call_id}"
            if isinstance(parsed, QuestionDraft):
                message.question = AgentQuestion(interaction_id=interaction_id, question=parsed.question, choices=parsed.choices)
            else:
                assert isinstance(parsed, InlineQuizDraft)
                message.inline_quiz = InlineChatQuiz(interaction_id=interaction_id, question=parsed.question,
                                                     choices=parsed.choices, correct_index=parsed.correct_index)
            run.awaiting_answer = True
            result = {"status": "awaiting_answer", "interaction_id": interaction_id,
                      "message": "The card is ready. Clew will send the learner's answer in a separate turn."}
        elif tool == "create_closure_quiz":
            assert isinstance(parsed, ClosureQuizDraft)
            if run.quiz_topic_id and parsed.topic_id != run.quiz_topic_id:
                raise ValueError("The test must be for the requested topic.")
            config = runtime.repository.current().workspace.config
            count = run.quiz_count or config.quiz_question_count
            questions = [QuizQuestion(id=f"{call_id}-{index}", prompt=q.prompt, choices=q.choices,
                         correct_choice_index=q.correct_choice_index, explanation=q.explanation)
                         for index, q in enumerate(parsed.questions)]
            session = QuizService(runtime.settings).start_session(graph, parsed.topic_id, count, questions=questions, generator=run.model)
            session.session_id = f"quiz-{call_id}"
            runtime.repository.save_quiz_session(session)
            run.quiz_session = session
            message.closure_quiz = public_quiz(session)
            result = {"status": "ready", "session_id": session.session_id, "topic_id": session.topic_id,
                      "question_count": session.question_count, "message": "The learner takes the test in Clew. Clew grades it and awards completion."}
        elif tool == "submit_blindspot_synthesis":
            assert isinstance(parsed, StudyBookSynthesisDraft)
            run.blindspot_synthesis = parsed
            result = {"status": "ready", "topic_count": len(parsed.topics)}
        else:
            raise ValueError("Unknown Clew tool.")
        message.activity.status = "completed"
        runtime.publish_message(run, message)
        output = json.dumps(result, ensure_ascii=False)
    except Exception as exc:
        message.activity.status = "failed"
        message.activity.detail = str(exc)
        for widget in (message.question, message.inline_quiz):
            if widget and widget.status == "pending":
                widget.status = "interrupted"
        runtime.publish_message(run, message)
        output = json.dumps({"error": str(exc)}, ensure_ascii=False)
    runtime.store.save_tool_result(call_id, run.thread_key, canonical, {"output": output})
    return output
