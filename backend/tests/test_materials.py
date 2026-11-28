from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter

from app.agent.contracts import CLOSURE_QUIZ_TOOLS, MATERIAL_TOOLS, tool_specs
from app.agent.runtime import AgentRuntime
from app.core.config import Settings
from app.models.domain import CreateGraphRequest, GraphChatRequest, MaterialSource, TopicKeyFile
from app.services.material_service import MaterialError, MaterialService
from app.services.repository import GraphRepository


def _create_sample_pdf(path: Path, text: str) -> None:
    """Create a tiny valid PDF with extractable text using pypdf + content stream."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    font_ref = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref}),
    })
    stream = DecodedStreamObject()
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream.set_data(f"BT /F1 12 Tf 20 150 Td ({escaped}) Tj ET".encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as fh:
        writer.write(fh)


class FakeAuth:
    def status(self, locale: str = "en") -> dict:
        return {"authenticated": True, "sharing": True, "account": "test@example.com"}

    async def close(self) -> None:
        return None


class FakeClient:
    def __init__(self, responses: list[dict] | None = None):
        self.responses = list(responses or [])
        self.requests: list[dict] = []

    async def list_models(self) -> list[dict]:
        return [{"slug": "gpt-test", "display_name": "GPT Test", "description": ""}]

    async def stream(self, payload: dict, on_event) -> dict:
        self.requests.append(payload)
        if not self.responses:
            return {"output": [{"type": "message", "id": "m-1", "content": [{"type": "output_text", "text": "done"}]}]}
        return self.responses.pop(0)


class MaterialGroundingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.root = Path(self.tmpdir.name)
        self.repo_dir = self.root / "milvus_sample"
        (self.repo_dir / "internal" / "querynode").mkdir(parents=True)
        (self.repo_dir / ".git").mkdir()
        (self.repo_dir / ".git" / "config").write_text("secret-git-config", encoding="utf-8")
        (self.repo_dir / "internal" / "querynode" / "segment.go").write_text(
            "package querynode\n\n// Search executes vector search on a segment.\nfunc Search(ctx string) error {\n\treturn nil\n}\n",
            encoding="utf-8",
        )
        _create_sample_pdf(self.repo_dir / "milvus_paper.pdf", "Milvus uses Log Broker and Knowhere for vector search.")
        self.outside_file = self.root / "outside_secret.txt"
        self.outside_file.write_text("top-secret", encoding="utf-8")
        (self.repo_dir / "escape_link.txt").symlink_to(self.outside_file)

        self.db_path = self.root / "test.sqlite3"
        self.settings = Settings(db_path=self.db_path)
        self.repo = GraphRepository(self.db_path)
        env = self.repo.create_graph(CreateGraphRequest(title="Milvus", subject="Vector DB", language="zh-CN"))
        self.graph_id = env.workspace.graphs[-1].graph_id

    def test_material_service_lists_searches_reads_code_and_pdf_and_blocks_escape(self) -> None:
        source = MaterialSource(id="mat-1", label="milvus_sample", path=str(self.repo_dir))
        self.repo.add_material_source(self.graph_id, source)
        graph = self.repo.graph(self.graph_id)
        service = MaterialService()

        listed = service.list_files(graph)
        paths = [entry["path"] for entry in listed["entries"]]
        self.assertIn("internal/querynode/segment.go", paths)
        self.assertIn("milvus_paper.pdf", paths)
        self.assertNotIn(".git/config", paths)
        self.assertNotIn("escape_link.txt", paths)

        search_code = service.search_text(graph, "Search executes vector")
        self.assertEqual(len(search_code["matches"]), 1)
        self.assertEqual(search_code["matches"][0]["path"], "internal/querynode/segment.go")
        self.assertEqual(search_code["matches"][0]["line"], 3)

        search_pdf = service.search_text(graph, "Knowhere")
        self.assertEqual(len(search_pdf["matches"]), 1)
        self.assertEqual(search_pdf["matches"][0]["path"], "milvus_paper.pdf")
        self.assertEqual(search_pdf["matches"][0]["page"], 1)

        code_slice = service.read_slice(graph, source_id="mat-1", path="internal/querynode/segment.go", start=3, end=5)
        self.assertEqual(code_slice["kind"], "text")
        self.assertIn("4: func Search(ctx string) error {", code_slice["content"])

        pdf_slice = service.read_slice(graph, source_id="mat-1", path="milvus_paper.pdf", start=1, end=1)
        self.assertEqual(pdf_slice["kind"], "pdf")
        self.assertIn("Knowhere", pdf_slice["pages"][0]["text"])

        with self.assertRaises(MaterialError):
            service.read_slice(graph, source_id="mat-1", path="../outside_secret.txt")
        with self.assertRaises(MaterialError):
            service.read_slice(graph, source_id="mat-1", path="escape_link.txt")

    def test_tool_specs_and_runtime_expose_materials_only_when_bound(self) -> None:
        names_without = {t["name"] for t in tool_specs(include_materials=False)}
        names_with = {t["name"] for t in tool_specs(include_materials=True)}
        self.assertTrue(MATERIAL_TOOLS.isdisjoint(names_without))
        self.assertTrue(MATERIAL_TOOLS.issubset(names_with))

        quiz_with_materials = {t["name"] for t in tool_specs(CLOSURE_QUIZ_TOOLS, include_materials=True)}
        self.assertTrue(MATERIAL_TOOLS.issubset(quiz_with_materials))

        # Bind source and run a chat turn invoking read_material
        source = MaterialSource(id="mat-1", label="milvus_sample", path=str(self.repo_dir))
        self.repo.add_material_source(self.graph_id, source)
        client = FakeClient(responses=[
            {"output": [{"type": "function_call", "call_id": "c-read-1", "name": "read_material", "arguments": json.dumps({"path": "internal/querynode/segment.go", "start": 1, "end": 6})}]},
            {"output": [{"type": "message", "id": "m-ans", "content": [{"type": "output_text", "text": "See segment.go:4"}]}]},
        ])
        runtime = AgentRuntime(self.settings, self.repo, auth=FakeAuth(), client=client)

        async def run_chat():
            sid, run_id = await runtime.start_chat(self.graph_id, GraphChatRequest(prompt="Explain Search"))
            run = runtime.runs.get(run_id)
            if run is not None:
                await run.done
            return sid

        asyncio.run(run_chat())
        # Verify material tools were passed to the model
        first_tools = {t["name"] for t in client.requests[0]["tools"] if t["type"] == "function"}
        self.assertTrue(MATERIAL_TOOLS.issubset(first_tools))
        # Verify function_call_output contains the real source line
        second_input = json.dumps(client.requests[1]["input"], ensure_ascii=False)
        self.assertIn("func Search(ctx string) error", second_input)

    def test_repository_material_and_key_file_lifecycle_creates_snapshots(self) -> None:
        from app.agent.contracts import GraphOperationDraft, ProposalDraft, ProposalTopicDraft
        from app.services.proposal_service import ProposalService

        graph = self.repo.graph(self.graph_id)
        draft = ProposalDraft(
            base_graph_version=graph.version,
            summary="Add QueryNode",
            operations=[
                GraphOperationDraft(
                    op_id="op-qn",
                    op="upsert_topic",
                    entity_kind="topic",
                    topic=ProposalTopicDraft(id="querynode", title="QueryNode", slug="querynode"),
                )
            ],
        )
        prepared = ProposalService().prepare(graph, draft, tool="propose_ingest", proposal_id="p-qn", prompt="seed", model="gpt-test", use_grounding=False)
        self.repo.apply_proposal(prepared.proposal_envelope)

        source = MaterialSource(id="mat-1", label="milvus_sample", path=str(self.repo_dir))
        self.repo.add_material_source(self.graph_id, source)
        kf = TopicKeyFile(id="kf-1", source_id="mat-1", path="internal/querynode/segment.go", note="Core search")
        self.repo.add_topic_key_file(self.graph_id, "querynode", kf)

        topic = next(t for t in self.repo.graph(self.graph_id).topics if t.id == "querynode")
        self.assertEqual(len(topic.key_files), 1)
        self.assertEqual(topic.key_files[0].path, "internal/querynode/segment.go")

        # Removing the material source cleans up dependent key_files cleanly
        self.repo.remove_material_source(self.graph_id, "mat-1")
        topic_after = next(t for t in self.repo.graph(self.graph_id).topics if t.id == "querynode")
        self.assertEqual(len(topic_after.key_files), 0)
        self.assertEqual(len(self.repo.graph(self.graph_id).material_sources), 0)


if __name__ == "__main__":
    unittest.main()
