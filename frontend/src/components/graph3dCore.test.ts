// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

import type { Edge, Topic, Zone } from "../lib/types";
import { buildGraph3DLayout } from "./graph3dCore";

function makeTopic(id: string, title = id, level = 0, zones: string[] = []): Topic {
  return {
    id,
    title,
    slug: id,
    description: "",
    difficulty: 1,
    estimated_minutes: 20,
    level,
    state: "not_started",
    zones,
    resources: [],
    artifacts: [],
  };
}

function makeEdge(id: string, source_topic_id: string, target_topic_id: string): Edge {
  return {
    id,
    source_topic_id,
    target_topic_id,
    relation: "requires",
    rationale: "",
  };
}

describe("buildGraph3DLayout stratified terrace layout", () => {
  it("places prerequisite targets strictly higher in Y than sources", () => {
    const topics = [
      makeTopic("root", "Root", 0, ["z1"]),
      makeTopic("mid", "Mid", 1, ["z1"]),
      makeTopic("leaf", "Leaf", 2, ["z2"]),
    ];
    const edges = [
      makeEdge("e1", "root", "mid"),
      makeEdge("e2", "mid", "leaf"),
    ];
    const zones: Zone[] = [
      { id: "z1", title: "Zone 1", kind: "module", color: "#c85a32", intensity: 0.5, topic_ids: ["root", "mid"] },
      { id: "z2", title: "Zone 2", kind: "module", color: "#3f7d58", intensity: 0.5, topic_ids: ["leaf"] },
    ];

    const layout = buildGraph3DLayout(topics, edges, zones);
    const pRoot = layout.positions.get("root")!;
    const pMid = layout.positions.get("mid")!;
    const pLeaf = layout.positions.get("leaf")!;

    expect(pMid.y).toBeGreaterThan(pRoot.y);
    expect(pLeaf.y).toBeGreaterThan(pMid.y);
    expect(layout.tierElevations.length).toBe(3);
  });

  it("keeps different zones separated horizontally in X-Z", () => {
    const topics = [
      makeTopic("a1", "A1", 0, ["za"]),
      makeTopic("a2", "A2", 1, ["za"]),
      makeTopic("b1", "B1", 0, ["zb"]),
      makeTopic("b2", "B2", 1, ["zb"]),
    ];
    const edges = [makeEdge("ea", "a1", "a2"), makeEdge("eb", "b1", "b2")];
    const zones: Zone[] = [
      { id: "za", title: "Zone A", kind: "module", color: "#c85a32", intensity: 0.5, topic_ids: ["a1", "a2"] },
      { id: "zb", title: "Zone B", kind: "module", color: "#3f7d58", intensity: 0.5, topic_ids: ["b1", "b2"] },
    ];

    const layout = buildGraph3DLayout(topics, edges, zones);
    const centerA = layout.zoneCenters.get("za")!;
    const centerB = layout.zoneCenters.get("zb")!;
    const zoneDist = Math.hypot(centerA.x - centerB.x, centerA.z - centerB.z);
    expect(zoneDist).toBeGreaterThan(100);
    // Same tier topics across different zones share exact Y elevation.
    expect(layout.positions.get("a1")!.y).toBe(layout.positions.get("b1")!.y);
    expect(layout.positions.get("a2")!.y).toBe(layout.positions.get("b2")!.y);
  });

  it("handles cyclic prerequisite edges without NaN coordinates", () => {
    const topics = [makeTopic("t1"), makeTopic("t2")];
    const edges = [makeEdge("c1", "t1", "t2"), makeEdge("c2", "t2", "t1")];
    const layout = buildGraph3DLayout(topics, edges, []);
    for (const pos of layout.positions.values()) {
      expect(Number.isFinite(pos.x)).toBe(true);
      expect(Number.isFinite(pos.y)).toBe(true);
      expect(Number.isFinite(pos.z)).toBe(true);
    }
  });
});
