from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models.domain import StudyGraph


class RenameGraphRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class GraphLayoutPositionRequest(BaseModel):
    x: float
    y: float


class UpdateGraphLayoutRequest(BaseModel):
    positions: dict[str, GraphLayoutPositionRequest]


class TopicResourceInput(BaseModel):
    url: str = Field(min_length=1, max_length=4000)


class TopicArtifactInput(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    body: str = Field(min_length=1, max_length=12000)


class CreateSessionRequest(BaseModel):
    topic_id: str | None = None
    title: str | None = None


class GraphExportRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    include_progress: bool = True
    format: Literal[
        "mapmind_graph_export",
        "mapmind_obsidian_export",
        "mapmind_study_book_html",
        "mapmind_study_book_md",
    ] = "mapmind_graph_export"
    obsidian: "ObsidianExportOptions | None" = None
    study_book: "StudyBookExportOptions | None" = None
    model: str | None = None


class GraphExportPackage(BaseModel):
    kind: str = "mapmind_graph_export"
    version: int = 1
    exported_at: str
    source_graph_id: str
    title: str
    include_progress: bool
    graph: StudyGraph


class ObsidianExportOptions(BaseModel):
    use_folders_as_zones: bool = True
    include_descriptions: bool = True
    include_resources: bool = True
    include_artifacts: bool = True


class StudyBookExportOptions(BaseModel):
    mode: Literal["handbook", "blindspots_only"] = "handbook"
    zone_ids: list[str] = Field(default_factory=list)
    include_notes: bool = True
    include_mistakes: bool = True
    include_chat_qa: bool = True
    ai_synthesize_blindspots: bool = False


class StudyBookBlindspotItem(BaseModel):
    misconception: str
    correction: str


class StudyBookExportPackage(BaseModel):
    kind: Literal["mapmind_study_book_export"] = "mapmind_study_book_export"
    version: int = 1
    exported_at: str
    source_graph_id: str
    title: str
    format: Literal["html", "markdown"]
    mode: Literal["handbook", "blindspots_only"]
    filename: str
    mime_type: str
    chapter_count: int
    topic_count: int
    mistake_count: int
    qa_count: int
    content: str


class ObsidianExportFile(BaseModel):
    path: str = Field(min_length=1)
    body: str


class ObsidianGraphExportPackage(BaseModel):
    kind: str = "mapmind_obsidian_export"
    version: int = 1
    exported_at: str
    source_graph_id: str
    title: str
    include_progress: bool
    folder_name: str
    file_count: int
    files: list[ObsidianExportFile] = Field(default_factory=list)


class GraphImportRequest(BaseModel):
    package: GraphExportPackage
    title: str | None = Field(default=None, max_length=120)
    include_progress: bool = True
