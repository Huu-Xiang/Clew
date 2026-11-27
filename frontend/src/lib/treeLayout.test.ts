import { describe, expect, it } from "vitest";

import { computeTreeLayout } from "./treeLayout";
import type { Edge, Topic, Zone } from "./types";

function makeGraph() {
  const topics = [
    { id: "root", title: "Transactions", level: 0 },
    { id: "iso", title: "Isolation Levels", level: 1 },
    { id: "mvcc", title: "MVCC", level: 2 },
    { id: "locks", title: "Locks", level: 2 },
  ] as Topic[];
  const edges = [
    { id: "e1", source_topic_id: "root", target_topic_id: "iso", relation: "requires", rationale: "" },
    { id: "e2", source_topic_id: "iso", target_topic_id: "mvcc", relation: "requires", rationale: "" },
    { id: "e3", source_topic_id: "iso", target_topic_id: "locks", relation: "requires", rationale: "" },
  ] as Edge[];
  const zones = [{ id: "z1", title: "Core", kind: "module", color: "#d97757", intensity: 0.5, topic_ids: ["root", "iso", "mvcc", "locks"] }] as Zone[];
  return { topics, edges, zones };
}

describe("computeTreeLayout", () => {
  it("layers prerequisites top-to-bottom in vertical mode without overlapping siblings", () => {
    const pos = computeTreeLayout(makeGraph(), "vertical");
    expect(pos.root.y).toBeLessThan(pos.iso.y);
    expect(pos.iso.y).toBeLessThan(pos.mvcc.y);
    expect(pos.mvcc.y).toBe(pos.locks.y);
    expect(Math.abs(pos.mvcc.x - pos.locks.x)).toBeGreaterThanOrEqual(150);
  });

  it("layers prerequisites left-to-right in horizontal mode", () => {
    const pos = computeTreeLayout(makeGraph(), "horizontal");
    expect(pos.root.x).toBeLessThan(pos.iso.x);
    expect(pos.iso.x).toBeLessThan(pos.mvcc.x);
    expect(pos.mvcc.x).toBe(pos.locks.x);
    expect(Math.abs(pos.mvcc.y - pos.locks.y)).toBeGreaterThanOrEqual(80);
  });
});
