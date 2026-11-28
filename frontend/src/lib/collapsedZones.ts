import type { Edge, Zone } from "./types";

export const COLLAPSED_ZONES_STORAGE_PREFIX = "clew_collapsed_zones_v1:";

export function readStoredCollapsedZones(graphId: string | null | undefined): string[] {
  if (!graphId || typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(`${COLLAPSED_ZONES_STORAGE_PREFIX}${graphId}`);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return Array.from(new Set(parsed.filter((item): item is string => typeof item === "string" && item.length > 0)));
  } catch {
    return [];
  }
}

export function writeStoredCollapsedZones(graphId: string | null | undefined, zoneIds: Iterable<string>): void {
  if (!graphId || typeof window === "undefined") return;
  try {
    const unique = Array.from(new Set(zoneIds));
    if (unique.length === 0) {
      window.localStorage.removeItem(`${COLLAPSED_ZONES_STORAGE_PREFIX}${graphId}`);
    } else {
      window.localStorage.setItem(`${COLLAPSED_ZONES_STORAGE_PREFIX}${graphId}`, JSON.stringify(unique));
    }
  } catch {
    // Ignore storage quota errors in private mode.
  }
}

export type AggregatedMacroEdge = {
  id: string;
  sourceId: string; // either a topic.id or `zone:${zone.id}`
  targetId: string; // either a topic.id or `zone:${zone.id}`
  sourceIsMacro: boolean;
  targetIsMacro: boolean;
  sourceZoneId: string | null;
  targetZoneId: string | null;
  count: number;
  hasRequires: boolean;
  originalEdgeIds: string[];
};

export function macroNodeId(zoneId: string): string {
  return `zone:${zoneId}`;
}

export function parseMacroNodeId(id: string): string | null {
  return id.startsWith("zone:") ? id.slice(5) : null;
}

/**
 * Given topics, edges, zones, and the set of currently collapsed zone IDs,
 * compute visible topic IDs and deduplicated edges (routing collapsed topics to `zone:<zoneId>`).
 */
export function buildCollapsedGraphProjection<T extends { id: string; zones?: string[] }>(params: {
  topics: T[];
  edges: Edge[];
  zones: Zone[];
  collapsedZoneIds: ReadonlySet<string>;
}): {
  visibleTopics: T[];
  collapsedZones: Zone[];
  topicToCollapsedZoneId: Map<string, string>;
  projectedEdges: AggregatedMacroEdge[];
} {
  const { topics, edges, zones, collapsedZoneIds } = params;
  const validTopicIds = new Set(topics.map((t) => t.id));
  const primaryZoneByTopic = new Map<string, string>();
  for (const zone of zones) {
    for (const tid of zone.topic_ids) {
      if (validTopicIds.has(tid) && !primaryZoneByTopic.has(tid)) {
        primaryZoneByTopic.set(tid, zone.id);
      }
    }
  }
  for (const topic of topics) {
    if (!primaryZoneByTopic.has(topic.id) && topic.zones?.length) {
      primaryZoneByTopic.set(topic.id, topic.zones[0]);
    }
  }

  const collapsedZones = zones.filter(
    (z) => collapsedZoneIds.has(z.id) && z.topic_ids.some((tid) => primaryZoneByTopic.get(tid) === z.id),
  );
  const activeCollapsedSet = new Set(collapsedZones.map((z) => z.id));

  const topicToCollapsedZoneId = new Map<string, string>();
  const visibleTopics: T[] = [];
  for (const topic of topics) {
    const zid = primaryZoneByTopic.get(topic.id);
    if (zid && activeCollapsedSet.has(zid)) {
      topicToCollapsedZoneId.set(topic.id, zid);
    } else {
      visibleTopics.push(topic);
    }
  }

  const edgeBuckets = new Map<string, AggregatedMacroEdge>();
  for (const edge of edges) {
    if (!validTopicIds.has(edge.source_topic_id) || !validTopicIds.has(edge.target_topic_id)) continue;
    const srcCollapsedZone = topicToCollapsedZoneId.get(edge.source_topic_id) ?? null;
    const tgtCollapsedZone = topicToCollapsedZoneId.get(edge.target_topic_id) ?? null;
    // Hide edges strictly internal to the same collapsed zone.
    if (srcCollapsedZone && tgtCollapsedZone && srcCollapsedZone === tgtCollapsedZone) {
      continue;
    }
    const sourceId = srcCollapsedZone ? macroNodeId(srcCollapsedZone) : edge.source_topic_id;
    const targetId = tgtCollapsedZone ? macroNodeId(tgtCollapsedZone) : edge.target_topic_id;
    if (sourceId === targetId) continue;

    const key = `${sourceId}>>>${targetId}`;
    const existing = edgeBuckets.get(key);
    if (existing) {
      existing.count += 1;
      if (edge.relation === "requires") existing.hasRequires = true;
      existing.originalEdgeIds.push(edge.id);
    } else {
      edgeBuckets.set(key, {
        id: existing ? edge.id : `proj:${key}`,
        sourceId,
        targetId,
        sourceIsMacro: Boolean(srcCollapsedZone),
        targetIsMacro: Boolean(tgtCollapsedZone),
        sourceZoneId: primaryZoneByTopic.get(edge.source_topic_id) ?? null,
        targetZoneId: primaryZoneByTopic.get(edge.target_topic_id) ?? null,
        count: 1,
        hasRequires: edge.relation === "requires",
        originalEdgeIds: [edge.id],
      });
    }
  }

  return {
    visibleTopics,
    collapsedZones,
    topicToCollapsedZoneId,
    projectedEdges: Array.from(edgeBuckets.values()),
  };
}
