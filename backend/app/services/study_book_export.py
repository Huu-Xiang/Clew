from __future__ import annotations

import html
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.models.api import (
    StudyBookBlindspotItem,
    StudyBookExportOptions,
    StudyBookExportPackage,
)
from app.models.domain import GraphChatThread, QuizQuestionReview, StudyGraph, Topic, Zone


INVALID_FILENAME_CHARS_RE = re.compile(r'[\\/:*?"<>|]+')
WHITESPACE_RE = re.compile(r"\s+")
SYNTHETIC_DISTILL_PREFIXES = (
    "请调用 propose_distillation",
    "请提炼我关于",
    "Distill this conversation",
    "Please call propose_distillation",
    "Distill only my personal blindspots",
)
MISTAKE_REVIEW_PROMPT_MARKERS = (
    "做错了以下测验题",
    "missed these quiz questions",
)
BLINDSPOT_KEYWORDS = (
    "卡点",
    "纠偏",
    "错题",
    "误区",
    "盲区",
    "misconception",
    "mistake",
    "confusion",
    "correction",
)

BOOK_COPY = {
    "en": {
        "handbook_subtitle": "Personal Knowledge Handbook",
        "blindspots_subtitle": "Personal Blindspots & Mistake Cheat Sheet",
        "unassigned_zone": "Additional Topics",
        "summary_heading": "Overview",
        "chapters": "Chapters",
        "sections": "Topics",
        "mistakes": "Missed Questions",
        "qa_items": "Personal Q&A",
        "toc": "Table of Contents",
        "chapter_prefix": "Chapter {index}",
        "section_prefix": "{chapter}.{section}",
        "core_notes": "Core Concept & Study Notes",
        "saved_notes": "Saved Notes",
        "resources": "Resources",
        "mistakes_heading": "Pitfalls & Quiz Mistakes",
        "qa_heading": "My Chat Questions & Clarifications",
        "ai_blindspots_heading": "Personal Blindspots & Corrections",
        "mistake_review_label": "Asked AI to review quiz mistakes",
        "your_answer": "Your answer",
        "correct_answer": "Correct answer",
        "explanation": "Why",
        "misconception_col": "Confusion / Trap",
        "correction_col": "Correction / Key Rule",
        "latest_quiz": "Latest quiz {score}%",
        "passed": "Passed",
        "not_passed": "Needs review",
        "prerequisites": "Prerequisites",
        "empty_blindspots_title": "No mistakes or study questions recorded yet",
        "empty_blindspots_body": "Take a topic quiz or ask follow-up questions in topic chat, then export again to build your personal cheat sheet.",
        "search_placeholder": "Search topics, mistakes, Q&A...",
        "filter_all": "All sections",
        "filter_weak": "Weak spots only",
        "toggle_theme": "Theme",
        "print_pdf": "Print / Save PDF",
        "badge_mistakes": "{count} missed",
        "badge_qa": "{count} Q&A",
        "question_prefix": "Q",
        "answer_prefix": "A",
        "states": {
            "not_started": "Not started",
            "learning": "Learning",
            "shaky": "Shaky",
            "solid": "Solid",
            "mastered": "Mastered",
            "needs_review": "Needs review",
        },
    },
    "zh-CN": {
        "handbook_subtitle": "个人专属知识通关小册子",
        "blindspots_subtitle": "个人薄弱点与错题突击小抄",
        "unassigned_zone": "其他主题",
        "summary_heading": "小册概览",
        "chapters": "章节数",
        "sections": "收录主题",
        "mistakes": "历史错题",
        "qa_items": "对话追问",
        "toc": "目录",
        "chapter_prefix": "第 {index} 章",
        "section_prefix": "{chapter}.{section}",
        "core_notes": "核心概念与学习笔记",
        "saved_notes": "已保存笔记",
        "resources": "参考资料",
        "mistakes_heading": "我踩过的坑 & 错题复盘",
        "qa_heading": "我的对话追问与解答",
        "ai_blindspots_heading": "个人盲区与纠偏对照表",
        "mistake_review_label": "请求 AI 复盘测验错题",
        "your_answer": "你的选择",
        "correct_answer": "正确答案",
        "explanation": "解析",
        "misconception_col": "当时的误区 / 卡点",
        "correction_col": "纠偏与关键结论",
        "latest_quiz": "最近测验 {score}%",
        "passed": "已通过",
        "not_passed": "待巩固",
        "prerequisites": "先修主题",
        "empty_blindspots_title": "当前范围内还没有错题或对话困惑记录",
        "empty_blindspots_body": "可以先做一次主题测验或在主题对话里追问几轮，再回来导出你的专属错题小抄。",
        "search_placeholder": "搜索章节、错题、对话困惑…",
        "filter_all": "全部章节",
        "filter_weak": "只看错题与追问",
        "toggle_theme": "切换明暗",
        "print_pdf": "打印 / 导出 PDF",
        "badge_mistakes": "错 {count} 题",
        "badge_qa": "追问 {count} 轮",
        "question_prefix": "问",
        "answer_prefix": "答",
        "states": {
            "not_started": "未开始",
            "learning": "学习中",
            "shaky": "尚不熟练",
            "solid": "已掌握",
            "mastered": "熟练掌握",
            "needs_review": "待复习",
        },
    },
}


@dataclass
class _TopicQAItem:
    question: str
    answer: str


@dataclass
class _BookSection:
    chapter_index: int
    section_index: int
    topic: Topic
    prerequisites: list[str] = field(default_factory=list)
    mistakes: list[QuizQuestionReview] = field(default_factory=list)
    legacy_missed_prompts: list[str] = field(default_factory=list)
    latest_score: float | None = None
    latest_passed: bool | None = None
    qa_items: list[_TopicQAItem] = field(default_factory=list)
    ai_blindspots: list[StudyBookBlindspotItem] = field(default_factory=list)
    has_weak_signal: bool = False


@dataclass
class _BookChapter:
    index: int
    zone_id: str
    title: str
    sections: list[_BookSection] = field(default_factory=list)


def _primary_zone_id(topic: Topic, *, zones_by_id: dict[str, Zone], zones: list[Zone]) -> str:
    for zid in topic.zones:
        if zid in zones_by_id:
            return zid
    for zone in zones:
        if topic.id in zone.topic_ids:
            return zone.id
    return "__unassigned__"


def _compute_global_topic_ranks(graph: StudyGraph) -> dict[str, int]:
    topic_ids = [t.id for t in graph.topics]
    topic_idx = {tid: i for i, tid in enumerate(topic_ids)}
    adj: dict[str, list[str]] = defaultdict(list)
    indeg: dict[str, int] = {tid: 0 for tid in topic_ids}
    outdeg: dict[str, int] = {tid: 0 for tid in topic_ids}
    for edge in graph.edges:
        if edge.relation != "requires":
            continue
        if edge.source_topic_id in indeg and edge.target_topic_id in indeg and edge.source_topic_id != edge.target_topic_id:
            adj[edge.source_topic_id].append(edge.target_topic_id)
            indeg[edge.target_topic_id] += 1
            outdeg[edge.source_topic_id] += 1

    remaining = set(topic_ids)
    rank: dict[str, int] = {tid: 0 for tid in topic_ids}
    order: list[str] = []
    while remaining:
        ready = sorted(
            [tid for tid in remaining if indeg[tid] == 0],
            key=lambda tid: (rank[tid], topic_idx[tid]),
        )
        if ready:
            curr = ready[0]
        else:
            curr = min(
                remaining,
                key=lambda tid: (-(outdeg[tid] - indeg[tid]), topic_idx[tid]),
            )
        remaining.remove(curr)
        order.append(curr)
        for nxt in adj[curr]:
            if nxt in remaining:
                indeg[nxt] -= 1
                rank[nxt] = max(rank[nxt], rank[curr] + 1)
    return {tid: idx for idx, tid in enumerate(order)}


def _order_zone_ids(
    graph: StudyGraph,
    zone_ids_to_order: list[str],
    topic_zone_map: dict[str, str],
) -> list[str]:
    zone_order_idx = {z.id: i for i, z in enumerate(graph.zones)}
    zone_order_idx["__unassigned__"] = len(graph.zones) + 1
    real_zones = [zid for zid in zone_ids_to_order if zid != "__unassigned__"]
    has_unassigned = "__unassigned__" in zone_ids_to_order
    if len(real_zones) <= 1:
        return real_zones + (["__unassigned__"] if has_unassigned else [])

    real_set = set(real_zones)
    adj: dict[str, set[str]] = defaultdict(set)
    indeg: dict[str, int] = {zid: 0 for zid in real_zones}
    outdeg: dict[str, int] = {zid: 0 for zid in real_zones}
    for edge in graph.edges:
        if edge.relation != "requires":
            continue
        sz = topic_zone_map.get(edge.source_topic_id)
        tz = topic_zone_map.get(edge.target_topic_id)
        if sz in real_set and tz in real_set and sz != tz and tz not in adj[sz]:
            adj[sz].add(tz)
            indeg[tz] += 1
            outdeg[sz] += 1

    remaining = set(real_zones)
    ordered: list[str] = []
    while remaining:
        ready = sorted([zid for zid in remaining if indeg[zid] == 0], key=lambda zid: zone_order_idx[zid])
        if ready:
            curr = ready[0]
        else:
            curr = min(remaining, key=lambda zid: (-(outdeg[zid] - indeg[zid]), zone_order_idx[zid]))
        remaining.remove(curr)
        ordered.append(curr)
        for nxt in adj[curr]:
            if nxt in remaining:
                indeg[nxt] -= 1
    if has_unassigned:
        ordered.append("__unassigned__")
    return ordered


def _order_topics_in_chapter(
    chapter_topics: list[Topic],
    graph: StudyGraph,
    global_rank: dict[str, int],
) -> list[Topic]:
    if len(chapter_topics) <= 1:
        return list(chapter_topics)
    topic_by_id = {t.id: t for t in chapter_topics}
    ids = [t.id for t in chapter_topics]
    id_set = set(ids)
    adj: dict[str, list[str]] = defaultdict(list)
    indeg: dict[str, int] = {tid: 0 for tid in ids}
    outdeg: dict[str, int] = {tid: 0 for tid in ids}
    for edge in graph.edges:
        if edge.relation == "requires" and edge.source_topic_id in id_set and edge.target_topic_id in id_set:
            if edge.source_topic_id != edge.target_topic_id:
                adj[edge.source_topic_id].append(edge.target_topic_id)
                indeg[edge.target_topic_id] += 1
                outdeg[edge.source_topic_id] += 1

    remaining = set(ids)
    ordered: list[Topic] = []
    while remaining:
        ready = sorted(
            [tid for tid in remaining if indeg[tid] == 0],
            key=lambda tid: (global_rank.get(tid, 0), topic_by_id[tid].level, tid),
        )
        if ready:
            curr = ready[0]
        else:
            curr = min(
                remaining,
                key=lambda tid: (-(outdeg[tid] - indeg[tid]), global_rank.get(tid, 0), tid),
            )
        remaining.remove(curr)
        ordered.append(topic_by_id[curr])
        for nxt in adj[curr]:
            if nxt in remaining:
                indeg[nxt] -= 1
    return ordered


def _collect_topic_mistakes(
    graph: StudyGraph,
    topic_id: str,
) -> tuple[list[QuizQuestionReview], list[str], float | None, bool | None]:
    attempts = [a for a in graph.quiz_attempts if a.topic_id == topic_id]
    if not attempts:
        return [], [], None, None
    latest = attempts[-1]
    seen_prompts: set[str] = set()
    reviews: list[QuizQuestionReview] = []
    legacy_prompts: list[str] = []

    for attempt in reversed(attempts):
        for rev in attempt.missed_reviews:
            key = rev.prompt.strip().casefold()
            if key and key not in seen_prompts:
                seen_prompts.add(key)
                reviews.append(rev)
        for prompt_text in attempt.missed_questions:
            key = prompt_text.strip().casefold()
            if key and key not in seen_prompts:
                seen_prompts.add(key)
                legacy_prompts.append(prompt_text.strip())
    return reviews, legacy_prompts, latest.score, latest.passed


def _collect_topic_qa(
    threads: list[GraphChatThread],
    topic_id: str,
    copy: dict[str, str],
) -> list[_TopicQAItem]:
    items: list[_TopicQAItem] = []
    for thread in threads:
        if thread.topic_id != topic_id:
            continue
        pending_question: str | None = None
        answer_parts: list[str] = []

        def flush_pair() -> None:
            nonlocal pending_question, answer_parts
            if pending_question and answer_parts:
                merged = "\n\n".join(answer_parts).strip()
                if len(merged) > 4000:
                    merged = merged[:3990].rstrip() + "…"
                items.append(_TopicQAItem(question=pending_question, answer=merged))
            pending_question = None
            answer_parts = []

        for msg in thread.messages:
            if msg.hidden:
                continue
            if msg.role == "user":
                flush_pair()
                text = msg.content.strip()
                if not text:
                    continue
                if any(text.startswith(prefix) for prefix in SYNTHETIC_DISTILL_PREFIXES):
                    pending_question = None
                    continue
                if any(marker in text for marker in MISTAKE_REVIEW_PROMPT_MARKERS):
                    pending_question = copy["mistake_review_label"]
                else:
                    pending_question = text if len(text) <= 500 else text[:490].rstrip() + "…"
            elif msg.role == "assistant" and pending_question is not None:
                if msg.message_phase == "commentary":
                    continue
                body = msg.content.strip()
                if body:
                    answer_parts.append(body)
        flush_pair()
    return items


def _topic_has_confusion_artifact(topic: Topic) -> bool:
    for art in topic.artifacts:
        haystack = f"{art.title}\n{art.body}".casefold()
        if any(kw in haystack for kw in BLINDSPOT_KEYWORDS):
            return True
    return False


def _assemble_chapters(
    graph: StudyGraph,
    threads: list[GraphChatThread],
    *,
    include_progress: bool,
    options: StudyBookExportOptions,
    ai_blindspots_by_topic: dict[str, list[StudyBookBlindspotItem]],
    copy: dict[str, str],
) -> list[_BookChapter]:
    zones_by_id = {z.id: z for z in graph.zones}
    topics_by_id = {t.id: t for t in graph.topics}
    topic_zone_map = {t.id: _primary_zone_id(t, zones_by_id=zones_by_id, zones=graph.zones) for t in graph.topics}

    valid_zone_ids = set(zones_by_id.keys())
    if any(t_zone == "__unassigned__" for t_zone in topic_zone_map.values()):
        valid_zone_ids.add("__unassigned__")

    if options.zone_ids:
        unknown = [zid for zid in options.zone_ids if zid not in valid_zone_ids]
        if unknown:
            raise ValueError(f"Unknown zone_ids for export: {', '.join(unknown)}")
        selected_zone_ids = list(dict.fromkeys(options.zone_ids))
    else:
        selected_zone_ids = [z.id for z in graph.zones if any(topic_zone_map[t.id] == z.id for t in graph.topics)]
        if any(topic_zone_map[t.id] == "__unassigned__" for t in graph.topics):
            selected_zone_ids.append("__unassigned__")

    ordered_zone_ids = _order_zone_ids(graph, selected_zone_ids, topic_zone_map)
    global_rank = _compute_global_topic_ranks(graph)

    prereq_titles: dict[str, list[str]] = defaultdict(list)
    for edge in graph.edges:
        if edge.relation == "requires":
            src = topics_by_id.get(edge.source_topic_id)
            if src is not None and src.title not in prereq_titles[edge.target_topic_id]:
                prereq_titles[edge.target_topic_id].append(src.title)

    chapters: list[_BookChapter] = []
    chapter_counter = 0
    for zid in ordered_zone_ids:
        zone_topics = [t for t in graph.topics if topic_zone_map[t.id] == zid]
        if not zone_topics:
            continue
        ordered_topics = _order_topics_in_chapter(zone_topics, graph, global_rank)
        sections: list[_BookSection] = []
        for topic in ordered_topics:
            mistakes, legacy_prompts, latest_score, latest_passed = (
                _collect_topic_mistakes(graph, topic.id)
                if (options.include_mistakes and include_progress)
                else ([], [], None, None)
            )
            qa_items = _collect_topic_qa(threads, topic.id, copy) if options.include_chat_qa else []
            ai_items = ai_blindspots_by_topic.get(topic.id, [])
            weak_signal = bool(
                mistakes
                or legacy_prompts
                or qa_items
                or ai_items
                or (include_progress and topic.state in {"shaky", "needs_review"})
                or _topic_has_confusion_artifact(topic)
            )
            if options.mode == "blindspots_only" and not weak_signal:
                continue
            sections.append(
                _BookSection(
                    chapter_index=0,
                    section_index=len(sections) + 1,
                    topic=topic,
                    prerequisites=prereq_titles.get(topic.id, []),
                    mistakes=mistakes,
                    legacy_missed_prompts=legacy_prompts,
                    latest_score=latest_score,
                    latest_passed=latest_passed,
                    qa_items=qa_items,
                    ai_blindspots=ai_items,
                    has_weak_signal=weak_signal,
                )
            )
        if not sections:
            continue
        chapter_counter += 1
        for sec_idx, sec in enumerate(sections, start=1):
            sec.chapter_index = chapter_counter
            sec.section_index = sec_idx
        zone_title = copy["unassigned_zone"] if zid == "__unassigned__" else zones_by_id[zid].title
        chapters.append(_BookChapter(index=chapter_counter, zone_id=zid, title=zone_title, sections=sections))
    return chapters


def collect_study_book_synthesis_inputs(
    graph: StudyGraph,
    threads: list[GraphChatThread],
    *,
    include_progress: bool,
    options: StudyBookExportOptions,
) -> list[dict]:
    """Extract compact per-topic mistake + chat confusion payloads for optional AI synthesis."""
    copy = BOOK_COPY["zh-CN" if graph.language == "zh-CN" else "en"]
    chapters = _assemble_chapters(
        graph,
        threads,
        include_progress=include_progress,
        options=options,
        ai_blindspots_by_topic={},
        copy=copy,
    )
    payloads: list[dict] = []
    for chapter in chapters:
        for sec in chapter.sections:
            if not sec.mistakes and not sec.legacy_missed_prompts and not sec.qa_items:
                continue
            payloads.append(
                {
                    "topic_id": sec.topic.id,
                    "title": sec.topic.title,
                    "mistakes": [
                        {
                            "prompt": m.prompt,
                            "your_answer": m.selected_choice,
                            "correct_answer": m.correct_choice,
                            "explanation": m.explanation,
                        }
                        for m in sec.mistakes[:6]
                    ],
                    "legacy_missed": sec.legacy_missed_prompts[:4],
                    "chat_qa": [
                        {"question": qa.question, "answer_excerpt": qa.answer[:600]}
                        for qa in sec.qa_items[:5]
                    ],
                }
            )
    return payloads[:25]


def _safe_filename(title: str, mode: str, ext: str) -> str:
    cleaned = INVALID_FILENAME_CHARS_RE.sub(" ", title).strip()
    cleaned = WHITESPACE_RE.sub("-", cleaned).strip("-") or "clew-study-book"
    suffix = "blindspots" if mode == "blindspots_only" else "study-book"
    return f"{cleaned[:80]}.{suffix}.{ext}"


def _render_markdown(
    *,
    title: str,
    subtitle: str,
    graph: StudyGraph,
    chapters: list[_BookChapter],
    include_progress: bool,
    options: StudyBookExportOptions,
    copy: dict[str, str],
) -> str:
    topic_count = sum(len(ch.sections) for ch in chapters)
    mistake_count = sum(len(sec.mistakes) + len(sec.legacy_missed_prompts) for ch in chapters for sec in ch.sections)
    qa_count = sum(len(sec.qa_items) for ch in chapters for sec in ch.sections)

    lines = [
        f"# {title}",
        "",
        f"> **{subtitle}** · {graph.subject}",
        "",
        f"## {copy['summary_heading']}",
        f"- {copy['chapters']}: {len(chapters)}",
        f"- {copy['sections']}: {topic_count}",
        f"- {copy['mistakes']}: {mistake_count}",
        f"- {copy['qa_items']}: {qa_count}",
    ]

    if not chapters:
        lines.extend(["", f"> [!NOTE] {copy['empty_blindspots_title']}", f"> {copy['empty_blindspots_body']}"])
        return "\n".join(lines).strip() + "\n"

    lines.extend(["", f"## {copy['toc']}"])
    for ch in chapters:
        ch_label = copy["chapter_prefix"].format(index=ch.index)
        lines.append(f"- **{ch_label}: {ch.title}**")
        for sec in ch.sections:
            sec_num = copy["section_prefix"].format(chapter=ch.index, section=sec.section_index)
            markers: list[str] = []
            m_count = len(sec.mistakes) + len(sec.legacy_missed_prompts)
            if m_count:
                markers.append(copy["badge_mistakes"].format(count=m_count))
            if sec.qa_items:
                markers.append(copy["badge_qa"].format(count=len(sec.qa_items)))
            suffix = f" ({', '.join(markers)})" if markers else ""
            lines.append(f"  - {sec_num} {sec.topic.title}{suffix}")

    for ch in chapters:
        ch_label = copy["chapter_prefix"].format(index=ch.index)
        lines.extend(["", "---", "", f"## {ch_label}：{ch.title}" if graph.language == "zh-CN" else f"## {ch_label}: {ch.title}"])
        for sec in ch.sections:
            sec_num = copy["section_prefix"].format(chapter=ch.index, section=sec.section_index)
            topic = sec.topic
            lines.extend(["", f"### {sec_num} {topic.title}"])
            meta_parts: list[str] = []
            if include_progress:
                state_label = copy["states"].get(topic.state, topic.state)
                meta_parts.append(state_label)
            if sec.latest_score is not None:
                status_text = copy["passed"] if sec.latest_passed else copy["not_passed"]
                meta_parts.append(f"{copy['latest_quiz'].format(score=round(sec.latest_score))} ({status_text})")
            if sec.prerequisites:
                meta_parts.append(f"{copy['prerequisites']}: {', '.join(sec.prerequisites)}")
            if meta_parts:
                lines.append(f"*{' · '.join(meta_parts)}*")

            if options.include_notes:
                if topic.description.strip():
                    lines.extend(["", topic.description.strip()])
                if topic.artifacts:
                    lines.extend(["", f"#### {copy['saved_notes']}"])
                    for art in topic.artifacts:
                        lines.extend(["", f"**{art.title}**", "", art.body.strip()])
                if topic.resources:
                    lines.extend(["", f"#### {copy['resources']}"])
                    for res in topic.resources:
                        lines.append(f"- [{res.label}]({res.url})")

            if sec.ai_blindspots:
                lines.extend(["", f"#### {copy['ai_blindspots_heading']}"])
                lines.append(f"| {copy['misconception_col']} | {copy['correction_col']} |")
                lines.append("| --- | --- |")
                for pair in sec.ai_blindspots:
                    left = pair.misconception.replace("|", "\\|").replace("\n", " ")
                    right = pair.correction.replace("|", "\\|").replace("\n", " ")
                    lines.append(f"| {left} | {right} |")

            if sec.mistakes or sec.legacy_missed_prompts:
                lines.extend(["", f"> [!WARNING] {copy['mistakes_heading']}"])
                for idx, m in enumerate(sec.mistakes, start=1):
                    lines.append(f"> **{idx}. {m.prompt}**")
                    if m.selected_choice:
                        lines.append(f"> - {copy['your_answer']}: ~~{m.selected_choice}~~")
                    lines.append(f"> - {copy['correct_answer']}: **{m.correct_choice}**")
                    if m.explanation:
                        lines.append(f"> - {copy['explanation']}: {m.explanation}")
                    lines.append(">")
                for prompt_text in sec.legacy_missed_prompts:
                    lines.append(f"> - {prompt_text}")

            if sec.qa_items:
                lines.extend(["", f"#### {copy['qa_heading']}"])
                for qa in sec.qa_items:
                    lines.extend(["", f"**{copy['question_prefix']}：** {qa.question}", "", qa.answer])

    return "\n".join(lines).strip() + "\n"


def _format_inline_escaped(escaped_line: str) -> str:
    # Input MUST already be html.escape(..., quote=True).
    def replace_link(match: re.Match[str]) -> str:
        label = match.group(1)
        url = html.unescape(match.group(2)).strip()
        if not (url.startswith("https://") or url.startswith("http://")):
            return label
        safe_url = html.escape(url, quote=True)
        return f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer">{label}</a>'

    out = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", replace_link, escaped_line)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", out)
    return out


def _markdown_to_safe_html(raw_text: str) -> str:
    escaped = html.escape(raw_text or "", quote=True)
    lines = escaped.splitlines()
    blocks: list[str] = []
    in_code = False
    code_lines: list[str] = []
    list_mode: str | None = None
    list_items: list[str] = []
    para_lines: list[str] = []

    def flush_para() -> None:
        if para_lines:
            joined = "<br>".join(_format_inline_escaped(line) for line in para_lines)
            blocks.append(f"<p>{joined}</p>")
            para_lines.clear()

    def flush_list() -> None:
        nonlocal list_mode
        if list_items and list_mode:
            tag = list_mode
            items_html = "".join(f"<li>{_format_inline_escaped(item)}</li>" for item in list_items)
            blocks.append(f"<{tag}>{items_html}</{tag}>")
            list_items.clear()
            list_mode = None

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_para()
            flush_list()
            if in_code:
                blocks.append(f"<pre><code>{chr(10).join(code_lines)}</code></pre>")
                code_lines.clear()
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not stripped:
            flush_para()
            flush_list()
            continue
        if stripped.startswith("### "):
            flush_para()
            flush_list()
            blocks.append(f"<h5>{_format_inline_escaped(stripped[4:])}</h5>")
            continue
        if stripped.startswith("## "):
            flush_para()
            flush_list()
            blocks.append(f"<h4>{_format_inline_escaped(stripped[3:])}</h4>")
            continue
        if stripped.startswith("# "):
            flush_para()
            flush_list()
            blocks.append(f"<h4>{_format_inline_escaped(stripped[2:])}</h4>")
            continue
        if stripped.startswith("&gt; "):
            flush_para()
            flush_list()
            blocks.append(f"<blockquote>{_format_inline_escaped(stripped[5:])}</blockquote>")
            continue
        if stripped.startswith("- ") or stripped.startswith("* "):
            flush_para()
            if list_mode != "ul":
                flush_list()
                list_mode = "ul"
            list_items.append(stripped[2:])
            continue
        ol_match = re.match(r"^\d+\.\s+(.*)$", stripped)
        if ol_match:
            flush_para()
            if list_mode != "ol":
                flush_list()
                list_mode = "ol"
            list_items.append(ol_match.group(1))
            continue
        flush_list()
        para_lines.append(stripped)

    if in_code and code_lines:
        blocks.append(f"<pre><code>{chr(10).join(code_lines)}</code></pre>")
    flush_para()
    flush_list()
    return "\n".join(blocks)


def _render_html(
    *,
    title: str,
    subtitle: str,
    graph: StudyGraph,
    chapters: list[_BookChapter],
    include_progress: bool,
    options: StudyBookExportOptions,
    copy: dict[str, str],
) -> str:
    topic_count = sum(len(ch.sections) for ch in chapters)
    mistake_count = sum(len(sec.mistakes) + len(sec.legacy_missed_prompts) for ch in chapters for sec in ch.sections)
    qa_count = sum(len(sec.qa_items) for ch in chapters for sec in ch.sections)

    toc_html_parts: list[str] = []
    main_html_parts: list[str] = []

    for ch in chapters:
        ch_label = copy["chapter_prefix"].format(index=ch.index)
        toc_links: list[str] = []
        section_cards: list[str] = []
        for sec in ch.sections:
            sec_id = f"sec-{ch.index}-{sec.section_index}"
            sec_num = copy["section_prefix"].format(chapter=ch.index, section=sec.section_index)
            m_count = len(sec.mistakes) + len(sec.legacy_missed_prompts)
            q_count = len(sec.qa_items)
            weak_attr = "1" if sec.has_weak_signal else "0"

            badges: list[str] = []
            if m_count:
                badges.append(f'<span class="pill pill-warn">{html.escape(copy["badge_mistakes"].format(count=m_count))}</span>')
            if q_count:
                badges.append(f'<span class="pill pill-qa">{html.escape(copy["badge_qa"].format(count=q_count))}</span>')

            toc_links.append(
                f'<a class="toc-link" href="#{sec_id}" data-weak="{weak_attr}" data-title="{html.escape(sec.topic.title.lower(), quote=True)}">'
                f'<span class="toc-num">{html.escape(sec_num)}</span>'
                f'<span class="toc-text">{html.escape(sec.topic.title)}</span>'
                f'{"".join(badges)}</a>'
            )

            meta_pills: list[str] = []
            if include_progress:
                state_label = copy["states"].get(sec.topic.state, sec.topic.state)
                meta_pills.append(f'<span class="pill">{html.escape(state_label)}</span>')
            if sec.latest_score is not None:
                cls = "pill-ok" if sec.latest_passed else "pill-warn"
                meta_pills.append(
                    f'<span class="pill {cls}">{html.escape(copy["latest_quiz"].format(score=round(sec.latest_score)))}</span>'
                )
            if sec.prerequisites:
                meta_pills.append(
                    f'<span class="meta-prereq">{html.escape(copy["prerequisites"])}: {html.escape(", ".join(sec.prerequisites))}</span>'
                )

            blocks: list[str] = []
            if options.include_notes:
                if sec.topic.description.strip():
                    blocks.append(f'<div class="prose">{_markdown_to_safe_html(sec.topic.description)}</div>')
                if sec.topic.artifacts:
                    art_blocks = "".join(
                        f'<div class="note-card"><h4>{html.escape(art.title)}</h4><div class="prose">{_markdown_to_safe_html(art.body)}</div></div>'
                        for art in sec.topic.artifacts
                    )
                    blocks.append(f'<div class="subblock"><h3>{html.escape(copy["saved_notes"])}</h3>{art_blocks}</div>')
                if sec.topic.resources:
                    res_links = "".join(
                        f'<li>{_format_inline_escaped(f"[{html.escape(res.label)}]({html.escape(res.url)})")}</li>'
                        for res in sec.topic.resources
                    )
                    blocks.append(f'<div class="subblock"><h3>{html.escape(copy["resources"])}</h3><ul class="res-list">{res_links}</ul></div>')

            if sec.ai_blindspots:
                rows = "".join(
                    f'<tr><td>{_markdown_to_safe_html(p.misconception)}</td><td>{_markdown_to_safe_html(p.correction)}</td></tr>'
                    for p in sec.ai_blindspots
                )
                blocks.append(
                    f'<div class="callout callout-ai"><h3>{html.escape(copy["ai_blindspots_heading"])}</h3>'
                    f'<table class="blindspot-table"><thead><tr><th>{html.escape(copy["misconception_col"])}</th>'
                    f'<th>{html.escape(copy["correction_col"])}</th></tr></thead><tbody>{rows}</tbody></table></div>'
                )

            if sec.mistakes or sec.legacy_missed_prompts:
                m_items: list[str] = []
                for idx, m in enumerate(sec.mistakes, start=1):
                    wrong_html = (
                        f'<div class="m-wrong">{html.escape(copy["your_answer"])}: <span>{html.escape(m.selected_choice)}</span></div>'
                        if m.selected_choice
                        else ""
                    )
                    exp_html = (
                        f'<div class="m-exp">{html.escape(copy["explanation"])}: {html.escape(m.explanation)}</div>'
                        if m.explanation
                        else ""
                    )
                    m_items.append(
                        f'<div class="mistake-item"><div class="m-q">{idx}. {html.escape(m.prompt)}</div>'
                        f'{wrong_html}<div class="m-right">{html.escape(copy["correct_answer"])}: <strong>{html.escape(m.correct_choice)}</strong></div>'
                        f'{exp_html}</div>'
                    )
                for prompt_text in sec.legacy_missed_prompts:
                    m_items.append(f'<div class="mistake-item"><div class="m-q">{html.escape(prompt_text)}</div></div>')
                blocks.append(
                    f'<div class="callout callout-warn"><h3>{html.escape(copy["mistakes_heading"])}</h3>{"".join(m_items)}</div>'
                )

            if sec.qa_items:
                qa_html = "".join(
                    f'<div class="qa-item"><div class="qa-q"><span class="qa-tag">{html.escape(copy["question_prefix"])}</span>'
                    f'<span>{html.escape(qa.question)}</span></div>'
                    f'<div class="qa-a prose">{_markdown_to_safe_html(qa.answer)}</div></div>'
                    for qa in sec.qa_items
                )
                blocks.append(f'<div class="callout callout-qa"><h3>{html.escape(copy["qa_heading"])}</h3>{qa_html}</div>')

            searchable = f"{sec.topic.title} {sec.topic.description} {' '.join(m.prompt for m in sec.mistakes)} {' '.join(q.question for q in sec.qa_items)}".lower()
            section_cards.append(
                f'<section id="{sec_id}" class="book-section" data-weak="{weak_attr}" data-search="{html.escape(searchable, quote=True)}">'
                f'<div class="section-head"><span class="sec-num">{html.escape(sec_num)}</span>'
                f'<h2>{html.escape(sec.topic.title)}</h2></div>'
                f'<div class="section-meta">{"".join(meta_pills)}</div>'
                f'{"".join(blocks)}</section>'
            )

        toc_html_parts.append(
            f'<div class="toc-group"><div class="toc-chapter">{html.escape(ch_label)} · {html.escape(ch.title)}</div>'
            f'{"".join(toc_links)}</div>'
        )
        main_html_parts.append(
            f'<article class="book-chapter"><div class="chapter-kicker">{html.escape(ch_label)}</div>'
            f'<h1 class="chapter-title">{html.escape(ch.title)}</h1>{"".join(section_cards)}</article>'
        )

    if not chapters:
        main_html_parts.append(
            f'<div class="callout callout-qa"><h3>{html.escape(copy["empty_blindspots_title"])}</h3>'
            f'<p>{html.escape(copy["empty_blindspots_body"])}</p></div>'
        )

    lang_attr = "zh-CN" if graph.language == "zh-CN" else "en"
    return f"""<!doctype html>
<html lang="{lang_attr}" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} — {html.escape(subtitle)}</title>
<style>
:root {{ --bg:#faf8f4; --surface:#ffffff; --ink:#1f1d1a; --muted:#686056; --line:#e6dfd5; --accent:#b84c27; --warn-bg:#fff6ed; --warn-line:#efb98d; --qa-bg:#f2f6fa; --qa-line:#b6cbe0; --ai-bg:#f4f7f2; --ai-line:#b9cfb0; }}
html[data-theme="dark"] {{ --bg:#111417; --surface:#181c20; --ink:#eef1f4; --muted:#9da7b0; --line:#2a3036; --accent:#e07a54; --warn-bg:#251a14; --warn-line:#6e3f25; --qa-bg:#141d26; --qa-line:#2a455e; --ai-bg:#152019; --ai-line:#2d4a35; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.68 -apple-system,BlinkMacSystemFont,"PingFang SC","Noto Sans SC","Inter",sans-serif; }}
.layout {{ display:grid; grid-template-columns:300px minmax(0,1fr); min-height:100vh; }}
.sidebar {{ position:sticky; top:0; height:100vh; overflow-y:auto; padding:20px 16px; border-right:1px solid var(--line); background:var(--surface); }}
.brand-sub {{ font-size:12px; color:var(--accent); font-weight:600; letter-spacing:.03em; }}
.brand-title {{ margin:4px 0 12px; font-size:18px; line-height:1.3; }}
.search {{ width:100%; padding:8px 10px; border:1px solid var(--line); border-radius:8px; background:var(--bg); color:var(--ink); font-size:13px; margin-bottom:10px; }}
.toolbar {{ display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px; }}
.btn {{ border:1px solid var(--line); background:var(--bg); color:var(--ink); border-radius:7px; padding:5px 9px; font-size:12px; cursor:pointer; }}
.btn.active {{ background:var(--accent); color:#fff; border-color:var(--accent); }}
.toc-group {{ margin-bottom:14px; }}
.toc-chapter {{ font-size:12px; font-weight:700; color:var(--muted); margin-bottom:6px; }}
.toc-link {{ display:flex; align-items:center; gap:6px; padding:5px 7px; border-radius:6px; text-decoration:none; color:var(--ink); font-size:13px; }}
.toc-link:hover {{ background:var(--bg); }}
.toc-num {{ color:var(--muted); font-size:12px; min-width:28px; }}
.toc-text {{ flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.content {{ max-width:860px; width:100%; margin:0 auto; padding:34px 40px 80px; }}
.hero {{ padding-bottom:20px; border-bottom:1px solid var(--line); margin-bottom:28px; }}
.hero h1 {{ margin:6px 0; font-size:30px; line-height:1.25; }}
.stats {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:12px; }}
.stat {{ font-size:13px; color:var(--muted); background:var(--surface); border:1px solid var(--line); border-radius:999px; padding:3px 11px; }}
.book-chapter {{ margin-bottom:44px; }}
.chapter-kicker {{ font-size:12px; font-weight:700; color:var(--accent); text-transform:uppercase; letter-spacing:.05em; }}
.chapter-title {{ margin:4px 0 18px; font-size:24px; padding-bottom:10px; border-bottom:2px solid var(--line); }}
.book-section {{ background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:22px 24px; margin-bottom:18px; break-inside:avoid; }}
.section-head {{ display:flex; align-items:baseline; gap:10px; }}
.sec-num {{ font-size:14px; font-weight:700; color:var(--accent); }}
.section-head h2 {{ margin:0; font-size:19px; }}
.section-meta {{ display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin:8px 0 14px; font-size:12px; color:var(--muted); }}
.pill {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px; border:1px solid var(--line); background:var(--bg); color:var(--muted); }}
.pill-warn {{ background:var(--warn-bg); border-color:var(--warn-line); color:var(--accent); }}
.pill-qa {{ background:var(--qa-bg); border-color:var(--qa-line); color:#36638f; }}
.pill-ok {{ background:var(--ai-bg); border-color:var(--ai-line); color:#396b45; }}
.subblock {{ margin-top:14px; }}
.subblock h3, .callout h3 {{ margin:0 0 10px; font-size:14px; }}
.note-card {{ border-left:3px solid var(--line); padding:4px 0 4px 12px; margin-bottom:10px; }}
.note-card h4 {{ margin:0 0 4px; font-size:14px; }}
.callout {{ border:1px solid var(--line); border-radius:10px; padding:14px 16px; margin-top:14px; break-inside:avoid; }}
.callout-warn {{ background:var(--warn-bg); border-color:var(--warn-line); }}
.callout-qa {{ background:var(--qa-bg); border-color:var(--qa-line); }}
.callout-ai {{ background:var(--ai-bg); border-color:var(--ai-line); }}
.mistake-item {{ padding:8px 0; border-top:1px dashed var(--warn-line); }}
.mistake-item:first-of-type {{ border-top:none; padding-top:0; }}
.m-q {{ font-weight:600; margin-bottom:4px; }}
.m-wrong span {{ text-decoration:line-through; color:var(--accent); }}
.m-right {{ color:#2f6b40; }}
html[data-theme="dark"] .m-right {{ color:#7ad093; }}
.m-exp {{ color:var(--muted); font-size:13.5px; margin-top:3px; }}
.qa-item {{ padding:10px 0; border-top:1px dashed var(--qa-line); }}
.qa-item:first-of-type {{ border-top:none; padding-top:0; }}
.qa-q {{ display:flex; gap:8px; font-weight:600; margin-bottom:6px; }}
.qa-tag {{ display:inline-flex; align-items:center; justify-content:center; width:22px; height:22px; border-radius:6px; background:var(--accent); color:#fff; font-size:12px; flex-shrink:0; }}
.blindspot-table {{ width:100%; border-collapse:collapse; font-size:13.5px; }}
.blindspot-table th, .blindspot-table td {{ border:1px solid var(--ai-line); padding:8px 10px; text-align:left; vertical-align:top; }}
.prose p {{ margin:0 0 8px; }}
.prose pre {{ background:var(--bg); border:1px solid var(--line); padding:10px; border-radius:8px; overflow-x:auto; font-size:13px; }}
.prose code {{ background:var(--bg); padding:1px 5px; border-radius:4px; font-size:13px; }}
.hidden {{ display:none !important; }}
@media (max-width:900px) {{ .layout {{ grid-template-columns:1fr; }} .sidebar {{ position:static; height:auto; border-right:none; border-bottom:1px solid var(--line); }} .content {{ padding:20px; }} }}
@media print {{ .sidebar {{ display:none; }} .layout {{ display:block; }} .content {{ max-width:none; padding:0; }} .book-section, .callout {{ break-inside:avoid; }} }}
</style>
</head>
<body>
<div class="layout">
  <aside class="sidebar">
    <div class="brand-sub">{html.escape(subtitle)}</div>
    <h2 class="brand-title">{html.escape(title)}</h2>
    <input id="q" class="search" type="search" placeholder="{html.escape(copy["search_placeholder"], quote=True)}">
    <div class="toolbar">
      <button id="btnWeak" class="btn" type="button">{html.escape(copy["filter_weak"])}</button>
      <button id="btnTheme" class="btn" type="button">{html.escape(copy["toggle_theme"])}</button>
      <button id="btnPrint" class="btn" type="button">{html.escape(copy["print_pdf"])}</button>
    </div>
    <nav>{"".join(toc_html_parts)}</nav>
  </aside>
  <main class="content">
    <header class="hero">
      <div class="brand-sub">{html.escape(subtitle)} · {html.escape(graph.subject)}</div>
      <h1>{html.escape(title)}</h1>
      <div class="stats">
        <span class="stat">{html.escape(copy["chapters"])}: {len(chapters)}</span>
        <span class="stat">{html.escape(copy["sections"])}: {topic_count}</span>
        <span class="stat">{html.escape(copy["mistakes"])}: {mistake_count}</span>
        <span class="stat">{html.escape(copy["qa_items"])}: {qa_count}</span>
      </div>
    </header>
    {"".join(main_html_parts)}
  </main>
</div>
<script>
const qInput = document.getElementById('q');
const btnWeak = document.getElementById('btnWeak');
const btnTheme = document.getElementById('btnTheme');
const btnPrint = document.getElementById('btnPrint');
let weakOnly = false;
function applyFilters() {{
  const query = (qInput.value || '').trim().toLowerCase();
  document.querySelectorAll('.book-section').forEach((sec) => {{
    const matchText = !query || (sec.dataset.search || '').includes(query);
    const matchWeak = !weakOnly || sec.dataset.weak === '1';
    sec.classList.toggle('hidden', !(matchText && matchWeak));
  }});
  document.querySelectorAll('.toc-link').forEach((link) => {{
    const matchText = !query || (link.dataset.title || '').includes(query);
    const matchWeak = !weakOnly || link.dataset.weak === '1';
    link.classList.toggle('hidden', !(matchText && matchWeak));
  }});
}}
qInput.addEventListener('input', applyFilters);
btnWeak.addEventListener('click', () => {{ weakOnly = !weakOnly; btnWeak.classList.toggle('active', weakOnly); applyFilters(); }});
btnTheme.addEventListener('click', () => {{ const h = document.documentElement; h.dataset.theme = h.dataset.theme === 'dark' ? 'light' : 'dark'; }});
btnPrint.addEventListener('click', () => window.print());
</script>
</body>
</html>
"""


def build_study_book_export_package(
    graph: StudyGraph,
    threads: list[GraphChatThread],
    *,
    title: str,
    include_progress: bool,
    book_format: str,
    options: StudyBookExportOptions | None = None,
    ai_blindspots_by_topic: dict[str, list[StudyBookBlindspotItem]] | None = None,
) -> StudyBookExportPackage:
    resolved_options = options or StudyBookExportOptions()
    copy = BOOK_COPY["zh-CN" if graph.language == "zh-CN" else "en"]
    subtitle = (
        copy["blindspots_subtitle"]
        if resolved_options.mode == "blindspots_only"
        else copy["handbook_subtitle"]
    )
    chapters = _assemble_chapters(
        graph,
        threads,
        include_progress=include_progress,
        options=resolved_options,
        ai_blindspots_by_topic=ai_blindspots_by_topic or {},
        copy=copy,
    )
    topic_count = sum(len(ch.sections) for ch in chapters)
    mistake_count = sum(len(sec.mistakes) + len(sec.legacy_missed_prompts) for ch in chapters for sec in ch.sections)
    qa_count = sum(len(sec.qa_items) for ch in chapters for sec in ch.sections)

    if book_format == "html":
        content = _render_html(
            title=title,
            subtitle=subtitle,
            graph=graph,
            chapters=chapters,
            include_progress=include_progress,
            options=resolved_options,
            copy=copy,
        )
        ext = "html"
        mime_type = "text/html;charset=utf-8"
        fmt_literal = "html"
    else:
        content = _render_markdown(
            title=title,
            subtitle=subtitle,
            graph=graph,
            chapters=chapters,
            include_progress=include_progress,
            options=resolved_options,
            copy=copy,
        )
        ext = "md"
        mime_type = "text/markdown;charset=utf-8"
        fmt_literal = "markdown"

    return StudyBookExportPackage(
        exported_at=datetime.now(timezone.utc).isoformat(),
        source_graph_id=graph.graph_id,
        title=title,
        format=fmt_literal,
        mode=resolved_options.mode,
        filename=_safe_filename(title, resolved_options.mode, ext),
        mime_type=mime_type,
        chapter_count=len(chapters),
        topic_count=topic_count,
        mistake_count=mistake_count,
        qa_count=qa_count,
        content=content,
    )
