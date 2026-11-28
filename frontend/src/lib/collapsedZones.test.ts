// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";
import {
  buildCollapsedGraphProjection,
  macroNodeId,
  readStoredCollapsedZones,
  writeStoredCollapsedZones,
} from "./collapsedZones";

beforeEach(() => localStorage.clear());

describe("collapsedZones", () => {
  it("persists and reloads collapsed zone ids per graph", () => {
    expect(readStoredCollapsedZones("g1")).toEqual([]);
    writeStoredCollapsedZones("g1", ["z1", "z2", "z1"]);
    expect(readStoredCollapsedZones("g1")).toEqual(["z1", "z2"]);
    writeStoredCollapsedZones("g1", []);
    expect(readStoredCollapsedZones("g1")).toEqual([]);
  });

  it("aggregates cross-zone edges into macro edges and hides internal collapsed edges", () => {
    const topics = [
      { id: "a1", title: "A1", slug: "a1", description: "", difficulty: 0.2, estimated_minutes: 10, level: 0, state: "solid" as const, zones: ["za"], resources: [], artifacts: [] },
      { id: "a2", title: "A2", slug: "a2", description: "", difficulty: 0.3, estimated_minutes: 10, level: 1, state: "not_started" as const, zones: ["za"], resources: [], artifacts: [] },
      { id: "b1", title: "B1", slug: "b1", description: "", difficulty: 0.4, estimated_minutes: 10, level: 1, state: "not_started" as const, zones: ["zb"], resources: [], artifacts: [] },
      { id: "c1", title: "C1", slug: "c1", description: "", difficulty: 0.5, estimated_minutes: 10, level: 2, state: "not_started" as const, zones: ["zc"], resources: [], artifacts: [] },
    ];
    const edges = [
      { id: "in-a", source_topic_id: "a1", target_topic_id: "a2", relation: "requires", rationale: "" },
      { id: "ab-1", source_topic_id: "a1", target_topic_id: "b1", relation: "requires", rationale: "" },
      { id: "ab-2", source_topic_id: "a2", target_topic_id: "b1", relation: "supports", rationale: "" },
      { id: "bc-1", source_topic_id: "b1", target_topic_id: "c1", relation: "requires", rationale: "" },
    ];
    const zones = [
      { id: "za", title: "Zone A", kind: "module", color: "#e11d48", intensity: 0.5, topic_ids: ["a1", "a2"] },
      { id: "zb", title: "Zone B", kind: "module", color: "#2563eb", intensity: 0.5, topic_ids: ["b1"] },
      { id: "zc", title: "Zone C", kind: "module", color: "#059669", intensity: 0.5, topic_ids: ["c1"] },
    ];

    const proj = buildCollapsedGraphProjection({
      topics,
      edges,
      zones,
      collapsedZoneIds: new Set(["za", "zb"]),
    });

    expect(proj.visibleTopics.map((t) => t.id)).toEqual(["c1"]);
    expect(proj.collapsedZones.map((z) => z.id)).toEqual(["za", "zb"]);
    expect(proj.projectedEdges).toHaveLength(2);

    const macroAB = proj.projectedEdges.find((e) => e.sourceId === macroNodeId("za") && e.targetId === macroNodeId("zb"));
    expect(macroAB?.count).toBe(2);
    expect(macroAB?.hasRequires).toBe(true);

    const macroBC = proj.projectedEdges.find((e) => e.sourceId === macroNodeId("zb") && e.targetId === "c1");
    expect(macroBC?.count).toBe(1);
  });
});
