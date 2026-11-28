import { describe, expect, it } from "vitest";
import { computeTreeLayout } from "./treeLayout";

describe("computeTreeLayout", () => {
  it("layers prerequisites top-to-bottom in vertical mode and left-to-right in horizontal mode", () => {
    const graph = {
      topics: [
        { id: "root", title: "Root", slug: "root", description: "", difficulty: 0.2, estimated_minutes: 15, level: 0, state: "not_started" as const, zones: ["z1"], resources: [], artifacts: [] },
        { id: "midA", title: "Mid A", slug: "mid-a", description: "", difficulty: 0.4, estimated_minutes: 20, level: 1, state: "not_started" as const, zones: ["z1"], resources: [], artifacts: [] },
        { id: "midB", title: "Mid B", slug: "mid-b", description: "", difficulty: 0.4, estimated_minutes: 20, level: 1, state: "not_started" as const, zones: ["z1"], resources: [], artifacts: [] },
        { id: "leaf", title: "Leaf", slug: "leaf", description: "", difficulty: 0.6, estimated_minutes: 30, level: 2, state: "not_started" as const, zones: ["z1"], resources: [], artifacts: [] },
      ],
      edges: [
        { id: "e1", source_topic_id: "root", target_topic_id: "midA", relation: "requires", rationale: "" },
        { id: "e2", source_topic_id: "root", target_topic_id: "midB", relation: "requires", rationale: "" },
        { id: "e3", source_topic_id: "midA", target_topic_id: "leaf", relation: "requires", rationale: "" },
      ],
      zones: [{ id: "z1", title: "Zone 1", kind: "module", color: "#c86442", intensity: 0.5, topic_ids: ["root", "midA", "midB", "leaf"] }],
    };

    const vert = computeTreeLayout(graph, "vertical");
    expect(vert.root.y).toBeLessThan(vert.midA.y);
    expect(vert.midA.y).toBe(vert.midB.y);
    expect(Math.abs(vert.midA.x - vert.midB.x)).toBeGreaterThanOrEqual(150);
    expect(vert.midA.y).toBeLessThan(vert.leaf.y);

    const horiz = computeTreeLayout(graph, "horizontal");
    expect(horiz.root.x).toBeLessThan(horiz.midA.x);
    expect(horiz.midA.x).toBe(horiz.midB.x);
    expect(Math.abs(horiz.midA.y - horiz.midB.y)).toBeGreaterThanOrEqual(80);
    expect(horiz.midA.x).toBeLessThan(horiz.leaf.x);
  });

  it("keeps distinct zones in strictly non-overlapping bounding boxes across multi-zone graphs", () => {
    const graph = {
      topics: [
        { id: "db1", title: "ACID", slug: "acid", description: "", difficulty: 0.2, estimated_minutes: 15, level: 0, state: "not_started" as const, zones: ["db"], resources: [], artifacts: [] },
        { id: "db2", title: "WAL Log", slug: "wal", description: "", difficulty: 0.4, estimated_minutes: 20, level: 1, state: "not_started" as const, zones: ["db"], resources: [], artifacts: [] },
        { id: "db3", title: "3NF", slug: "3nf", description: "", difficulty: 0.4, estimated_minutes: 20, level: 2, state: "not_started" as const, zones: ["db"], resources: [], artifacts: [] },
        { id: "kf1", title: "Kafka Basics", slug: "kf1", description: "", difficulty: 0.3, estimated_minutes: 20, level: 1, state: "not_started" as const, zones: ["kafka"], resources: [], artifacts: [] },
        { id: "kf2", title: "CDC Pipeline", slug: "kf2", description: "", difficulty: 0.5, estimated_minutes: 25, level: 2, state: "not_started" as const, zones: ["kafka"], resources: [], artifacts: [] },
        { id: "fl1", title: "Flink State", slug: "fl1", description: "", difficulty: 0.5, estimated_minutes: 25, level: 2, state: "not_started" as const, zones: ["flink"], resources: [], artifacts: [] },
        { id: "fl2", title: "Checkpoint", slug: "fl2", description: "", difficulty: 0.6, estimated_minutes: 30, level: 3, state: "not_started" as const, zones: ["flink"], resources: [], artifacts: [] },
      ],
      edges: [
        { id: "e1", source_topic_id: "db1", target_topic_id: "db2", relation: "requires", rationale: "" },
        { id: "e2", source_topic_id: "db2", target_topic_id: "db3", relation: "requires", rationale: "" },
        { id: "e3", source_topic_id: "db2", target_topic_id: "kf2", relation: "requires", rationale: "" },
        { id: "e4", source_topic_id: "kf1", target_topic_id: "kf2", relation: "requires", rationale: "" },
        { id: "e5", source_topic_id: "kf2", target_topic_id: "fl1", relation: "requires", rationale: "" },
        { id: "e6", source_topic_id: "fl1", target_topic_id: "fl2", relation: "requires", rationale: "" },
      ],
      zones: [
        { id: "db", title: "Transactions", kind: "module", color: "#e11d48", intensity: 0.5, topic_ids: ["db1", "db2", "db3"] },
        { id: "kafka", title: "Kafka & CDC", kind: "module", color: "#2563eb", intensity: 0.5, topic_ids: ["kf1", "kf2"] },
        { id: "flink", title: "Flink", kind: "module", color: "#059669", intensity: 0.5, topic_ids: ["fl1", "fl2"] },
      ],
    };

    for (const dir of ["vertical", "horizontal"] as const) {
      const pos = computeTreeLayout(graph, dir);
      const boxes = graph.zones.map((z) => {
        const xs = z.topic_ids.map((id) => pos[id].x);
        const ys = z.topic_ids.map((id) => pos[id].y);
        return { id: z.id, minX: Math.min(...xs) - 50, maxX: Math.max(...xs) + 50, minY: Math.min(...ys) - 40, maxY: Math.max(...ys) + 40 };
      });
      for (let i = 0; i < boxes.length; i += 1) {
        for (let j = i + 1; j < boxes.length; j += 1) {
          const a = boxes[i];
          const b = boxes[j];
          const overlaps = a.minX <= b.maxX && a.maxX >= b.minX && a.minY <= b.maxY && a.maxY >= b.minY;
          expect(overlaps).toBe(false);
        }
      }
    }
  });
});
