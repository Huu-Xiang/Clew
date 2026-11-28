from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from agent_test_support import install_client
from app.models.api import StudyBookBlindspotItem, StudyBookExportOptions
from app.models.domain import (
    Artifact,
    ChatMessage,
    Edge,
    GraphChatThread,
    QuizAttempt,
    QuizQuestion,
    QuizQuestionReview,
    StudyGraph,
    Topic,
    Zone,
)
from app.services.quiz_service import QuizService
from app.services.study_book_export import build_study_book_export_package


def _sample_graph(*, language: str = "zh-CN") -> StudyGraph:
    return StudyGraph(
        graph_id="g-book",
        subject="Data Engineering",
        title="DE 面试准备",
        language=language,
        topics=[
            Topic(
                id="t-adv",
                title="MVCC 与快照隔离",
                slug="mvcc",
                description="多版本并发控制原理。",
                state="mastered",
                level=1,
                zones=["z-tx"],
            ),
            Topic(
                id="t-tx",
                title="事务边界与回滚 <script>alert(1)</script>",
                slug="tx-boundary",
                description="BEGIN / COMMIT / ROLLBACK 基础。",
                state="shaky",
                level=0,
                zones=["z-tx"],
                artifacts=[
                    Artifact(
                        id="art-1",
                        kind="note",
                        title="事务笔记",
                        body="## 核心理解\n事务是原子单元。\n\n## 我的卡点与纠偏\n- 误区：ROLLBACK 会自动判断业务失败\n- 纠偏：需要应用层检查影响行数",
                    )
                ],
            ),
            Topic(
                id="t-idx",
                title="B+ 树与联合索引",
                slug="btree-index",
                description="最左前缀与回表。",
                state="not_started",
                level=0,
                zones=["z-idx"],
            ),
        ],
        edges=[
            Edge(id="e1", source_topic_id="t-tx", target_topic_id="t-adv", relation="requires"),
            Edge(id="e2", source_topic_id="t-adv", target_topic_id="t-idx", relation="requires"),
        ],
        zones=[
            Zone(id="z-idx", title="索引原理", kind="module", color="#3f7d58", topic_ids=["t-idx"]),
            Zone(id="z-tx", title="事务与并发控制", kind="module", color="#c85a32", topic_ids=["t-tx", "t-adv"]),
        ],
        quiz_attempts=[
            QuizAttempt(
                id="a1",
                topic_id="t-tx",
                question_count=2,
                score=50.0,
                passed=False,
                missed_reviews=[
                    QuizQuestionReview(
                        question_id="q1",
                        prompt="UPDATE 影响 0 行时 ROLLBACK 会自动触发吗？",
                        selected_choice="会自动触发",
                        correct_choice="不会自动触发",
                        was_correct=False,
                        explanation="0 行受影响不是 SQL 语法或约束错误，需应用层主动回滚。",
                    )
                ],
            ),
            QuizAttempt(
                id="a2",
                topic_id="t-tx",
                question_count=3,
                score=67.0,
                passed=False,
                missed_reviews=[
                    QuizQuestionReview(
                        question_id="q1",
                        prompt="UPDATE 影响 0 行时 ROLLBACK 会自动触发吗？",
                        selected_choice="会自动触发",
                        correct_choice="不会自动触发",
                        was_correct=False,
                        explanation="0 行受影响不是 SQL 语法或约束错误，需应用层主动回滚。",
                    ),
                    QuizQuestionReview(
                        question_id="q2",
                        prompt="以下哪种情况会破坏原子性？",
                        selected_choice="长事务",
                        correct_choice="未开启事务的多条独立语句",
                        was_correct=False,
                        explanation="autocommit 下每条语句独立提交。",
                    ),
                ],
            ),
        ],
    )


def _sample_threads() -> list[GraphChatThread]:
    return [
        GraphChatThread(
            session_id="s-tx",
            graph_id="g-book",
            topic_id="t-tx",
            messages=[
                ChatMessage(id="m1", role="user", content="为什么 UPDATE 不存在的行不会自动回滚？<img src=x onerror=alert(1)>"),
                ChatMessage(id="m2", role="assistant", message_phase="commentary", content="thinking..."),
                ChatMessage(id="m3", role="assistant", message_phase="final_answer", content="因为 0 行匹配在 SQL 里属于正常执行结果，不算异常。"),
                ChatMessage(id="m4", role="user", content="请调用 propose_distillation 提炼我们关于「事务」的这段学习对话"),
                ChatMessage(id="m5", role="assistant", message_phase="final_answer", content="已为你生成对话提炼卡片。"),
            ],
        )
    ]


class StudyBookExportTests(unittest.TestCase):
    def test_handbook_orders_chapters_and_sections_by_prerequisites_and_dedupes_mistakes(self):
        graph = _sample_graph()
        threads = _sample_threads()
        pkg = build_study_book_export_package(
            graph,
            threads,
            title="DE 通关小册",
            include_progress=True,
            book_format="markdown",
            options=StudyBookExportOptions(mode="handbook"),
        )
        self.assertEqual(pkg.chapter_count, 2)
        self.assertEqual(pkg.topic_count, 3)
        self.assertEqual(pkg.mistake_count, 2)  # q1 deduplicated across attempts
        self.assertEqual(pkg.qa_count, 1)  # commentary & propose_distillation boilerplate filtered out

        # Chapter 1 must be 事务与并发控制 (prerequisite of 索引原理 via t-adv -> t-idx)
        tx_ch_pos = pkg.content.index("第 1 章：事务与并发控制")
        idx_ch_pos = pkg.content.index("第 2 章：索引原理")
        self.assertLess(tx_ch_pos, idx_ch_pos)

        # Within Chapter 1, t-tx must appear before t-adv
        tx_sec_pos = pkg.content.index("1.1 事务边界与回滚")
        adv_sec_pos = pkg.content.index("1.2 MVCC 与快照隔离")
        self.assertLess(tx_sec_pos, adv_sec_pos)

        self.assertIn("UPDATE 影响 0 行时 ROLLBACK 会自动触发吗？", pkg.content)
        self.assertIn("因为 0 行匹配在 SQL 里属于正常执行结果", pkg.content)
        self.assertNotIn("已为你生成对话提炼卡片", pkg.content)

    def test_blindspots_only_filters_out_untouched_topics_and_escapes_html_xss(self):
        graph = _sample_graph()
        threads = _sample_threads()
        pkg = build_study_book_export_package(
            graph,
            threads,
            title="DE 错题小抄",
            include_progress=True,
            book_format="html",
            options=StudyBookExportOptions(mode="blindspots_only"),
        )
        self.assertEqual(pkg.format, "html")
        self.assertEqual(pkg.mode, "blindspots_only")
        self.assertEqual(pkg.chapter_count, 1)
        self.assertEqual(pkg.topic_count, 1)
        self.assertIn("事务边界与回滚", pkg.content)
        self.assertNotIn("B+ 树与联合索引", pkg.content)
        # Strict XSS escaping
        self.assertNotIn("<script>alert(1)</script>", pkg.content)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", pkg.content)
        self.assertNotIn("<img src=x onerror=alert(1)>", pkg.content)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", pkg.content)

    def test_zone_filter_rejects_unknown_zone_fail_closed(self):
        graph = _sample_graph()
        with self.assertRaises(ValueError):
            build_study_book_export_package(
                graph,
                [],
                title="Bad Zone",
                include_progress=True,
                book_format="markdown",
                options=StudyBookExportOptions(zone_ids=["nonexistent-zone"]),
            )

    def test_api_export_endpoint_supports_study_book_and_optional_ai_synthesis(self):
        client, repo, runtime = install_client(self)
        graph = repo.graph("mathematics-demo")
        first_topic = graph.topics[0]
        # Save a quiz session and record a mistake so candidate payload is non-empty
        quiz_service = QuizService(runtime.settings)
        questions = [
            QuizQuestion(
                id=f"q{i}",
                prompt="What is a basis?" if i == 0 else f"Extra question {i}?",
                choices=["Any set", "Linearly independent spanning set", "Orthogonal only", "Empty"],
                correct_choice_index=1,
                explanation="Needs both independence and span.",
            )
            for i in range(6)
        ]
        quiz_sess = quiz_service.start_session(graph, first_topic.id, 6, questions=questions, generator="test-model")
        repo.save_quiz_session(quiz_sess)
        attempt, _, awarded_state, _ = quiz_service.grade_session(graph, quiz_sess, {f"q{i}": 0 for i in range(6)})
        repo.record_quiz_attempt(
            graph.graph_id,
            attempt,
            awarded_state,
            base_graph_version=graph.version,
            session_id=quiz_sess.session_id,
        )

        # 1) Deterministic 0-token HTML export
        resp = client.post(
            f"/api/v1/workspace/graphs/{graph.graph_id}/export",
            json={
                "format": "mapmind_study_book_html",
                "study_book": {"mode": "blindspots_only", "ai_synthesize_blindspots": False},
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["kind"], "mapmind_study_book_export")
        self.assertEqual(data["format"], "html")
        self.assertGreaterEqual(data["mistake_count"], 1)
        self.assertIn("What is a basis?", data["content"])

        # 2) Optional AI synthesis path
        runtime.synthesize_study_book_blindspots = AsyncMock(
            return_value={
                first_topic.id: [
                    StudyBookBlindspotItem(
                        misconception="Thought any spanning set is a basis",
                        correction="A basis must be both spanning AND linearly independent.",
                    )
                ]
            }
        )
        resp_ai = client.post(
            f"/api/v1/workspace/graphs/{graph.graph_id}/export",
            json={
                "format": "mapmind_study_book_md",
                "study_book": {"mode": "blindspots_only", "ai_synthesize_blindspots": True},
            },
        )
        self.assertEqual(resp_ai.status_code, 200)
        data_ai = resp_ai.json()
        self.assertEqual(data_ai["format"], "markdown")
        self.assertIn("Thought any spanning set is a basis", data_ai["content"])
        self.assertIn("A basis must be both spanning AND linearly independent.", data_ai["content"])
