import type { Edge, GraphEnvelope, Topic, Zone } from "./types";

export type TreeLayoutDirection = "vertical" | "horizontal";

export type LayoutPositions = Record<string, { x: number; y: number }>;

type LocalBoxLayout = {
  positions: LayoutPositions;
  width: number;
  height: number;
};

/**
 * Lay out a single subset of topics as a clean layered DAG centered around (0, 0) top-left (0..width, 0..height).
 */
function layoutSubgraph(
  topics: Topic[],
  edges: Edge[],
  direction: TreeLayoutDirection,
  zoneRankOf: (topicId: string) => number,
  entryBoostById?: ReadonlyMap<string, number>,
): LocalBoxLayout {
  if (topics.length === 0) {
    return { positions: {}, width: 0, height: 0 };
  }

  const topicIds = new Set(topics.map((t) => t.id));
  const topicById = new Map(topics.map((t) => [t.id, t]));

  const validEdges = edges.filter(
    (e) => e.source_topic_id !== e.target_topic_id && topicIds.has(e.source_topic_id) && topicIds.has(e.target_topic_id),
  );
  const requiresEdges = validEdges.filter((e) => e.relation === "requires");
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
  if (requiresEdges.length > 0) {
    for (const edge of validEdges) {
      if (edge.relation === "requires") continue;
      if (parentsById.get(edge.target_topic_id)!.length === 0 && childrenById.get(edge.target_topic_id)!.length === 0) {
        parentsById.get(edge.target_topic_id)!.push(edge.source_topic_id);
        childrenById.get(edge.source_topic_id)!.push(edge.target_topic_id);
      }
    }
  }

  // Bellman-Ford longest-path layering (cycle-safe).
  const layerById = new Map<string, number>();
  for (const topic of topics) {
    layerById.set(topic.id, 0);
  }
  for (let pass = 0; pass < topics.length; pass += 1) {
    let changed = false;
    for (const topic of topics) {
      for (const parentId of parentsById.get(topic.id) ?? []) {
        const candidate = (layerById.get(parentId) ?? 0) + 1;
        if (candidate > (layerById.get(topic.id) ?? 0) && candidate < topics.length) {
          layerById.set(topic.id, candidate);
          changed = true;
        }
      }
    }
    if (!changed) break;
  }

  const layersMap = new Map<number, string[]>();
  for (const topic of topics) {
    const layer = layerById.get(topic.id) ?? 0;
    const bucket = layersMap.get(layer);
    if (bucket) bucket.push(topic.id);
    else layersMap.set(layer, [topic.id]);
  }
  const layers = Array.from(layersMap.keys())
    .sort((a, b) => a - b)
    .map((idx) => layersMap.get(idx)!);

  layers[0].sort((a, b) => {
    const boostDiff = (entryBoostById?.get(b) ?? 0) - (entryBoostById?.get(a) ?? 0);
    if (boostDiff !== 0) return boostDiff;
    const zDiff = zoneRankOf(a) - zoneRankOf(b);
    if (zDiff !== 0) return zDiff;
    const degDiff = (childrenById.get(b)?.length ?? 0) - (childrenById.get(a)?.length ?? 0);
    if (degDiff !== 0) return degDiff;
    return (topicById.get(a)?.title ?? a).localeCompare(topicById.get(b)?.title ?? b);
  });

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
        const avgA =
          parentsA.length > 0
            ? parentsA.reduce((sum, p) => sum + (orderIndex.get(p) ?? 0), 0) / parentsA.length
            : zoneRankOf(a) * 100;
        const avgB =
          parentsB.length > 0
            ? parentsB.reduce((sum, p) => sum + (orderIndex.get(p) ?? 0), 0) / parentsB.length
            : zoneRankOf(b) * 100;
        if (Math.abs(avgA - avgB) > 1e-4) return avgA - avgB;
        const zDiff = zoneRankOf(a) - zoneRankOf(b);
        if (zDiff !== 0) return zDiff;
        return (topicById.get(a)?.title ?? a).localeCompare(topicById.get(b)?.title ?? b);
      });
      syncOrderIndex();
    }
    for (let i = layers.length - 2; i >= 0; i -= 1) {
      layers[i].sort((a, b) => {
        const childrenA = childrenById.get(a) ?? [];
        const childrenB = childrenById.get(b) ?? [];
        const avgA =
          childrenA.length > 0
            ? childrenA.reduce((sum, c) => sum + (orderIndex.get(c) ?? 0), 0) / childrenA.length
            : (orderIndex.get(a) ?? 0);
        const avgB =
          childrenB.length > 0
            ? childrenB.reduce((sum, c) => sum + (orderIndex.get(c) ?? 0), 0) / childrenB.length
            : (orderIndex.get(b) ?? 0);
        if (Math.abs(avgA - avgB) > 1e-4) return avgA - avgB;
        return zoneRankOf(a) - zoneRankOf(b);
      });
      syncOrderIndex();
    }
  }

  const rawPositions: LayoutPositions = {};
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;

  if (direction === "vertical") {
    const colGap = 185;
    const rowGap = 128;
    layers.forEach((row, layerIdx) => {
      const totalWidth = (row.length - 1) * colGap;
      const startX = -totalWidth / 2;
      const y = layerIdx * rowGap;
      row.forEach((topicId, colIdx) => {
        const x = startX + colIdx * colGap;
        rawPositions[topicId] = { x, y };
        minX = Math.min(minX, x);
        maxX = Math.max(maxX, x);
        minY = Math.min(minY, y);
        maxY = Math.max(maxY, y);
      });
    });
  } else {
    const colGap = 225;
    const rowGap = 94;
    layers.forEach((col, layerIdx) => {
      const totalHeight = (col.length - 1) * rowGap;
      const startY = -totalHeight / 2;
      const x = layerIdx * colGap;
      col.forEach((topicId, rowIdx) => {
        const y = startY + rowIdx * rowGap;
        rawPositions[topicId] = { x, y };
        minX = Math.min(minX, x);
        maxX = Math.max(maxX, x);
        minY = Math.min(minY, y);
        maxY = Math.max(maxY, y);
      });
    });
  }

  // Normalize local box so top-left is (0, 0).
  const positions: LayoutPositions = {};
  for (const [id, pt] of Object.entries(rawPositions)) {
    positions[id] = {
      x: Math.round(pt.x - minX),
      y: Math.round(pt.y - minY),
    };
  }
  return {
    positions,
    width: Math.max(0, Math.round(maxX - minX)),
    height: Math.max(0, Math.round(maxY - minY)),
  };
}

function assignPrimaryZoneByTopic(topics: Topic[], zones: Zone[]): Map<string, string> {
  const validZoneIds = new Set(zones.map((z) => z.id));
  const map = new Map<string, string>();
  for (const zone of zones) {
    for (const topicId of zone.topic_ids) {
      if (!map.has(topicId)) {
        map.set(topicId, zone.id);
      }
    }
  }
  for (const topic of topics) {
    if (!map.has(topic.id)) {
      const firstValid = (topic.zones ?? []).find((zid) => validZoneIds.has(zid));
      map.set(topic.id, firstValid ?? "__unzoned__");
    }
  }
  return map;
}

/**
 * Compute a clean layered DAG / tree layout for a Clew study graph.
 * When 2+ non-empty zones exist, uses a two-level compound layout:
 *   1) Layer zones as a non-overlapping macro-DAG (swimlanes / cards)
 *   2) Lay out each zone's internal topics as a tidy mini-tree inside its own disjoint territory
 * This guarantees zone convex hulls never overlap into a spiderweb while preserving directional flow.
 */
export function computeTreeLayout(
  graph: Pick<GraphEnvelope, "topics" | "edges" | "zones">,
  direction: TreeLayoutDirection = "vertical",
): LayoutPositions {
  const topics = graph.topics;
  if (topics.length === 0) return {};

  const primaryZoneByTopic = assignPrimaryZoneByTopic(topics, graph.zones);
  const zoneOrder = new Map<string, number>();
  graph.zones.forEach((z, idx) => zoneOrder.set(z.id, idx));
  zoneOrder.set("__unzoned__", graph.zones.length);
  const zoneRankOf = (topicId: string) => zoneOrder.get(primaryZoneByTopic.get(topicId) ?? "__unzoned__") ?? graph.zones.length;

  // Group topics by primary zone.
  const topicsByGroup = new Map<string, Topic[]>();
  for (const topic of topics) {
    const gid = primaryZoneByTopic.get(topic.id) ?? "__unzoned__";
    const list = topicsByGroup.get(gid);
    if (list) list.push(topic);
    else topicsByGroup.set(gid, [topic]);
  }

  const activeGroupIds = Array.from(topicsByGroup.keys()).sort(
    (a, b) => (zoneOrder.get(a) ?? 999) - (zoneOrder.get(b) ?? 999),
  );

  // Single-zone (or unzoned) graph -> direct single-tree layout centered on canvas.
  if (activeGroupIds.length <= 1) {
    const sub = layoutSubgraph(topics, graph.edges, direction, zoneRankOf);
    const originX = direction === "vertical" ? Math.round(560 - sub.width / 2) : 140;
    const originY = direction === "vertical" ? 120 : Math.round(380 - sub.height / 2);
    const out: LayoutPositions = {};
    for (const [id, pt] of Object.entries(sub.positions)) {
      out[id] = { x: originX + pt.x, y: originY + pt.y };
    }
    return out;
  }

  // Multi-zone graph -> build Zone Meta-DAG from cross-zone edges (`requires` weighted 3x over auxiliary edges).
  const topicIds = new Set(topics.map((t) => t.id));
  const validEdges = graph.edges.filter(
    (e) => e.source_topic_id !== e.target_topic_id && topicIds.has(e.source_topic_id) && topicIds.has(e.target_topic_id),
  );
  const pairWeight = new Map<string, number>();
  const entryBoostByTopic = new Map<string, number>();
  for (const edge of validEdges) {
    const gFrom = primaryZoneByTopic.get(edge.source_topic_id)!;
    const gTo = primaryZoneByTopic.get(edge.target_topic_id)!;
    if (gFrom === gTo) continue;
    const w = edge.relation === "requires" ? 3 : 1;
    const key = `${gFrom}>>>${gTo}`;
    pairWeight.set(key, (pairWeight.get(key) ?? 0) + w);
    entryBoostByTopic.set(edge.target_topic_id, (entryBoostByTopic.get(edge.target_topic_id) ?? 0) + w);
  }

  // Resolve opposing cross-zone pairs so the dominant prerequisite flow wins cleanly.
  const groupParents = new Map<string, string[]>();
  const groupChildren = new Map<string, string[]>();
  for (const gid of activeGroupIds) {
    groupParents.set(gid, []);
    groupChildren.set(gid, []);
  }
  for (let i = 0; i < activeGroupIds.length; i += 1) {
    for (let j = i + 1; j < activeGroupIds.length; j += 1) {
      const a = activeGroupIds[i];
      const b = activeGroupIds[j];
      const ab = pairWeight.get(`${a}>>>${b}`) ?? 0;
      const ba = pairWeight.get(`${b}>>>${a}`) ?? 0;
      if (ab === 0 && ba === 0) continue;
      if (ab >= ba) {
        groupParents.get(b)!.push(a);
        groupChildren.get(a)!.push(b);
      } else {
        groupParents.get(a)!.push(b);
        groupChildren.get(b)!.push(a);
      }
    }
  }

  // Longest-path macro-layer assignment on groups (cycle-safe).
  const groupLayer = new Map<string, number>();
  for (const gid of activeGroupIds) groupLayer.set(gid, 0);
  for (let pass = 0; pass < activeGroupIds.length; pass += 1) {
    let changed = false;
    for (const gid of activeGroupIds) {
      for (const p of groupParents.get(gid) ?? []) {
        const candidate = (groupLayer.get(p) ?? 0) + 1;
        if (candidate > (groupLayer.get(gid) ?? 0) && candidate < activeGroupIds.length) {
          groupLayer.set(gid, candidate);
          changed = true;
        }
      }
    }
    if (!changed) break;
  }

  // Compute each zone's local mini-tree box first.
  const boxByGroup = new Map<string, LocalBoxLayout>();
  for (const gid of activeGroupIds) {
    const groupTopics = topicsByGroup.get(gid) ?? [];
    boxByGroup.set(gid, layoutSubgraph(groupTopics, validEdges, direction, zoneRankOf, entryBoostByTopic));
  }

  // Group into macro-ranks; wrap wide macro-ranks (at most 3 zones per rank) so canvas stays balanced.
  const rawRanks = new Map<number, string[]>();
  for (const gid of activeGroupIds) {
    const r = groupLayer.get(gid) ?? 0;
    const list = rawRanks.get(r);
    if (list) list.push(gid);
    else rawRanks.set(r, [gid]);
  }
  const macroRanks: string[][] = [];
  const maxGroupsPerBand = 3;
  for (const r of Array.from(rawRanks.keys()).sort((a, b) => a - b)) {
    const row = rawRanks.get(r)!;
    row.sort((a, b) => {
      const degDiff = (groupChildren.get(b)?.length ?? 0) - (groupChildren.get(a)?.length ?? 0);
      if (degDiff !== 0) return degDiff;
      return (zoneOrder.get(a) ?? 999) - (zoneOrder.get(b) ?? 999);
    });
    for (let k = 0; k < row.length; k += maxGroupsPerBand) {
      macroRanks.push(row.slice(k, k + maxGroupsPerBand));
    }
  }

  // Pack zone boxes with generous hull-safe margins so convex hulls + header pills never collide!
  const positions: LayoutPositions = {};
  const zonePadX = 190;
  const zonePadY = 185;

  if (direction === "vertical") {
    let cursorY = 140;
    const centerX = 640;
    for (const band of macroRanks) {
      const boxes = band.map((gid) => ({ gid, box: boxByGroup.get(gid)! }));
      const totalBandWidth =
        boxes.reduce((sum, item) => sum + item.box.width, 0) + Math.max(0, boxes.length - 1) * zonePadX;
      let cursorX = centerX - totalBandWidth / 2;
      let maxBandHeight = 0;
      for (const { box } of boxes) {
        maxBandHeight = Math.max(maxBandHeight, box.height);
      }
      for (const { box } of boxes) {
        // Vertically center shorter zone boxes gently within the band's top half.
        const offsetY = cursorY;
        for (const [tid, pt] of Object.entries(box.positions)) {
          positions[tid] = {
            x: Math.round(cursorX + pt.x),
            y: Math.round(offsetY + pt.y),
          };
        }
        cursorX += box.width + zonePadX;
      }
      cursorY += maxBandHeight + zonePadY;
    }
  } else {
    let cursorX = 160;
    const centerY = 420;
    for (const band of macroRanks) {
      const boxes = band.map((gid) => ({ gid, box: boxByGroup.get(gid)! }));
      const totalBandHeight =
        boxes.reduce((sum, item) => sum + item.box.height, 0) + Math.max(0, boxes.length - 1) * zonePadY;
      let cursorY = centerY - totalBandHeight / 2;
      let maxBandWidth = 0;
      for (const { box } of boxes) {
        maxBandWidth = Math.max(maxBandWidth, box.width);
      }
      for (const { box } of boxes) {
        for (const [tid, pt] of Object.entries(box.positions)) {
          positions[tid] = {
            x: Math.round(cursorX + pt.x),
            y: Math.round(cursorY + pt.y),
          };
        }
        cursorY += box.height + zonePadY;
      }
      cursorX += maxBandWidth + zonePadX + 30;
    }
  }

  return positions;
}
