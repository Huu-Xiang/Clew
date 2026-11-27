import type { GraphEnvelope } from "./types";

export type TreeLayoutDirection = "vertical" | "horizontal";

export type LayoutPositions = Record<string, { x: number; y: number }>;

/**
 * Compute a clean layered DAG / tree layout for a Clew study graph.
 * Uses longest-path prerequisite layering plus barycenter ordering to minimize crossings.
 */
export function computeTreeLayout(
  graph: Pick<GraphEnvelope, "topics" | "edges" | "zones">,
  direction: TreeLayoutDirection = "vertical",
): LayoutPositions {
  const topics = graph.topics;
  if (topics.length === 0) return {};

  const topicIds = new Set(topics.map((topic) => topic.id));
  const topicById = new Map(topics.map((topic) => [topic.id, topic]));

  // Prefer `requires` edges for primary layering; fall back to all valid directed edges for otherwise unlinked nodes.
  const validEdges = graph.edges.filter(
    (edge) => edge.source_topic_id !== edge.target_topic_id && topicIds.has(edge.source_topic_id) && topicIds.has(edge.target_topic_id),
  );
  const requiresEdges = validEdges.filter((edge) => edge.relation === "requires");
  const primaryEdges = requiresEdges.length > 0 ? requiresEdges : validEdges;

  const parentsById = new Map<string, string[]>();
  const childrenById = new Map<string, string[]>();
  for (const topic of topics) {
    parentsById.set(topic.id, []);
    childrenById.set(topic.id, []);
  }
  for (const edge of primaryEdges) {
    parentsById.get(edge.target_topic_id)!.push(edge.source_topic_id);
    childrenById.get(edge.source_topic_id)!.push(edge.target_topic_id);
  }
  // If a topic had no `requires` edges at all, attach any auxiliary edges so it still layers sensibly.
  if (requiresEdges.length > 0) {
    for (const edge of validEdges) {
      if (edge.relation === "requires") continue;
      if (parentsById.get(edge.target_topic_id)!.length === 0 && childrenById.get(edge.target_topic_id)!.length === 0) {
        parentsById.get(edge.target_topic_id)!.push(edge.source_topic_id);
        childrenById.get(edge.source_topic_id)!.push(edge.target_topic_id);
      }
    }
  }

  // Assign layers via Bellman-Ford-style longest path relaxation (safe against accidental cycles).
  const layerById = new Map<string, number>();
  for (const topic of topics) {
    layerById.set(topic.id, 0);
  }
  const maxIterations = topics.length;
  for (let pass = 0; pass < maxIterations; pass += 1) {
    let changed = false;
    for (const topic of topics) {
      const parents = parentsById.get(topic.id) ?? [];
      for (const parentId of parents) {
        const candidate = (layerById.get(parentId) ?? 0) + 1;
        if (candidate > (layerById.get(topic.id) ?? 0) && candidate < topics.length) {
          layerById.set(topic.id, candidate);
          changed = true;
        }
      }
    }
    if (!changed) break;
  }

  // Stable zone ordering so topics from the same zone stay clustered together.
  const zoneRankByTopicId = new Map<string, number>();
  graph.zones.forEach((zone, zoneIndex) => {
    for (const topicId of zone.topic_ids) {
      if (!zoneRankByTopicId.has(topicId)) {
        zoneRankByTopicId.set(topicId, zoneIndex);
      }
    }
  });
  const zoneRank = (topicId: string) => zoneRankByTopicId.get(topicId) ?? graph.zones.length;

  const layersMap = new Map<number, string[]>();
  for (const topic of topics) {
    const layer = layerById.get(topic.id) ?? 0;
    const bucket = layersMap.get(layer);
    if (bucket) bucket.push(topic.id);
    else layersMap.set(layer, [topic.id]);
  }
  const sortedLayerIndices = Array.from(layersMap.keys()).sort((a, b) => a - b);
  const layers = sortedLayerIndices.map((idx) => layersMap.get(idx)!);

  // Initial sort for layer 0: group by zone, then hubs first, then title.
  layers[0].sort((a, b) => {
    const zDiff = zoneRank(a) - zoneRank(b);
    if (zDiff !== 0) return zDiff;
    const degDiff = (childrenById.get(b)?.length ?? 0) - (childrenById.get(a)?.length ?? 0);
    if (degDiff !== 0) return degDiff;
    return (topicById.get(a)?.title ?? a).localeCompare(topicById.get(b)?.title ?? b);
  });

  // Two passes of barycenter ordering to reduce edge crossings.
  const orderIndex = new Map<string, number>();
  const syncOrderIndex = () => {
    for (const row of layers) {
      row.forEach((id, idx) => orderIndex.set(id, idx));
    }
  };
  syncOrderIndex();

  for (let sweep = 0; sweep < 2; sweep += 1) {
    for (let i = 1; i < layers.length; i += 1) {
      layers[i].sort((a, b) => {
        const parentsA = parentsById.get(a) ?? [];
        const parentsB = parentsById.get(b) ?? [];
        const avgA = parentsA.length > 0
          ? parentsA.reduce((sum, p) => sum + (orderIndex.get(p) ?? 0), 0) / parentsA.length
          : zoneRank(a) * 100;
        const avgB = parentsB.length > 0
          ? parentsB.reduce((sum, p) => sum + (orderIndex.get(p) ?? 0), 0) / parentsB.length
          : zoneRank(b) * 100;
        if (Math.abs(avgA - avgB) > 1e-4) return avgA - avgB;
        const zDiff = zoneRank(a) - zoneRank(b);
        if (zDiff !== 0) return zDiff;
        return (topicById.get(a)?.title ?? a).localeCompare(topicById.get(b)?.title ?? b);
      });
      syncOrderIndex();
    }
    for (let i = layers.length - 2; i >= 0; i -= 1) {
      layers[i].sort((a, b) => {
        const childrenA = childrenById.get(a) ?? [];
        const childrenB = childrenById.get(b) ?? [];
        const avgA = childrenA.length > 0
          ? childrenA.reduce((sum, c) => sum + (orderIndex.get(c) ?? 0), 0) / childrenA.length
          : (orderIndex.get(a) ?? 0);
        const avgB = childrenB.length > 0
          ? childrenB.reduce((sum, c) => sum + (orderIndex.get(c) ?? 0), 0) / childrenB.length
          : (orderIndex.get(b) ?? 0);
        if (Math.abs(avgA - avgB) > 1e-4) return avgA - avgB;
        return zoneRank(a) - zoneRank(b);
      });
      syncOrderIndex();
    }
  }

  const positions: LayoutPositions = {};
  if (direction === "vertical") {
    const colGap = 185;
    const rowGap = 135;
    const originX = 560;
    const originY = 120;
    layers.forEach((row, layerIdx) => {
      const totalWidth = (row.length - 1) * colGap;
      const startX = originX - totalWidth / 2;
      const y = originY + layerIdx * rowGap;
      row.forEach((topicId, colIdx) => {
        positions[topicId] = {
          x: Math.round(startX + colIdx * colGap),
          y: Math.round(y),
        };
      });
    });
  } else {
    const colGap = 230;
    const rowGap = 96;
    const originX = 140;
    const originY = 380;
    layers.forEach((col, layerIdx) => {
      const totalHeight = (col.length - 1) * rowGap;
      const startY = originY - totalHeight / 2;
      const x = originX + layerIdx * colGap;
      col.forEach((topicId, rowIdx) => {
        positions[topicId] = {
          x: Math.round(x),
          y: Math.round(startY + rowIdx * rowGap),
        };
      });
    });
  }

  return positions;
}
