from __future__ import annotations

import unittest

from agent_test_support import install_client
from app.models.domain import QuizQuestion, TopicQuizSession
from app.services.quiz_service import QuizService


class QuizSkipAndReviewTests(unittest.TestCase):
    def _root_and_child(self, graph):
        targets = {e.target_topic_id for e in graph.edges if e.relation == "requires"}
        root = next(t.id for t in graph.topics if t.id not in targets)
        child = next(e.target_topic_id for e in graph.edges if e.relation == "requires" and e.source_topic_id == root)
        return root, child

    def test_skip_preserves_existing_quiz_attempts_and_unlocks_downstream(self):
        client, repo, runtime = install_client(self)
        graph = repo.graph("mathematics-demo")
        root_id, child_id = self._root_and_child(graph)
        quiz_service = QuizService(runtime.settings)

        # Record a failed real quiz attempt (67%) on root topic
        questions = [
            QuizQuestion(id=f"q{i}", prompt=f"Root question {i}?", choices=["A", "B", "C", "D"], correct_choice_index=0, explanation=f"Because A is right for {i}.")
            for i in range(6)
        ]
        session = quiz_service.start_session(graph, root_id, 6, questions=questions, generator="test-model")
        # 4/6 = 67% -> fails 75% threshold, 2 wrong answers
        answers = {f"q{i}": (0 if i < 4 else 1) for i in range(6)}
        attempt, _, awarded_state, reviews = quiz_service.grade_session(graph, session, answers)
        self.assertFalse(attempt.passed)
        self.assertEqual(len(attempt.missed_reviews), 2)
        self.assertEqual(len(attempt.asked_prompts), 6)
        self.assertEqual(attempt.missed_reviews[0].selected_choice, "B")
        self.assertEqual(attempt.missed_reviews[0].correct_choice, "A")

        repo.save_quiz_session(session)
        repo.record_quiz_attempt("mathematics-demo", attempt, awarded_state, base_graph_version=graph.version, session_id=session.session_id)

        # Downstream child topic is blocked before skip
        before = quiz_service.build_closure_status(repo.graph("mathematics-demo"), child_id)
        self.assertFalse(before.can_award_completion)

        # Skip / mark root finished via API
        res = client.post(f"/api/v1/graphs/mathematics-demo/topics/{root_id}/mark-finished")
        self.assertEqual(res.status_code, 200, res.text)
        updated_graph = repo.graph("mathematics-demo")

        # Topic is now solid, downstream is unlocked, AND real 67% attempt + missed_reviews are preserved
        root_topic = next(t for t in updated_graph.topics if t.id == root_id)
        self.assertEqual(root_topic.state, "solid")
        after = quiz_service.build_closure_status(updated_graph, child_id)
        self.assertTrue(after.can_award_completion)
        attempts = [a for a in updated_graph.quiz_attempts if a.topic_id == root_id]
        self.assertEqual(len(attempts), 1)
        self.assertAlmostEqual(attempts[0].score, 4 / 6)
        self.assertEqual(len(attempts[0].missed_reviews), 2)

    def test_retake_prompt_includes_prior_asked_prompts_to_avoid_repeats(self):
        client, repo, runtime = install_client(self)
        graph = repo.graph("mathematics-demo")
        root_id, _ = self._root_and_child(graph)
        quiz_service = QuizService(runtime.settings)

        questions = [
            QuizQuestion(id=f"q{i}", prompt=f"Unique prior question #{i}?", choices=["A", "B", "C", "D"], correct_choice_index=0, explanation="Exp")
            for i in range(6)
        ]
        session = quiz_service.start_session(graph, root_id, 6, questions=questions, generator="test-model")
        attempt, _, awarded_state, _ = quiz_service.grade_session(graph, session, {f"q{i}": 1 for i in range(6)})
        repo.save_quiz_session(session)
        repo.record_quiz_attempt("mathematics-demo", attempt, awarded_state, base_graph_version=graph.version, session_id=session.session_id)

        captured_prompts: list[str] = []
        original_execute = runtime._execute

        async def spy_execute(run, previous_messages):
            captured_prompts.append(run.request.prompt)
            run.quiz_session = session
            runtime.finish(run, "completed")

        runtime._execute = spy_execute
        try:
            res = client.post(f"/api/v1/graphs/mathematics-demo/topics/{root_id}/quiz/start", json={})
            self.assertEqual(res.status_code, 200, res.text)
            self.assertEqual(len(captured_prompts), 1)
            self.assertIn("Unique prior question #0?", captured_prompts[0])
            self.assertIn("Do NOT repeat", captured_prompts[0])
        finally:
            runtime._execute = original_execute
