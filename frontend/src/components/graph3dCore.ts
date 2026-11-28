import type { Edge, Topic, Zone } from "../lib/types";
import { hashString } from "./graphCanvasCore";

export type GraphPoint3D = { x: number; y: number; z: number };

export type Graph3DLayout = {
  positions: Map<string, GraphPoint3D>;
  center: GraphPoint3D;
  radius: number;
  zoneCenters: Map<string, GraphPoint3D>;
  tiers: Map<string, number>;
  tierElevations: number[];
};

const TIER_SPACING = 52;

function computeGlobalTiers(topics: Topic[], edges: Edge[]): Map<string, number> {
  const topicIds = topics.map((t) => t.id);
  const topicIdx = new Map(topics.map((t, i) => [t.id, i]));
  const adj = new Map<string, string[]>();
  const indeg = new Map<string, number>();
  const outdeg = new Map<string, number>();
  const tier = new Map<string, number>();

  for (const id of topicIds) {
    adj.set(id, []);
    indeg.set(id, 0);
    outdeg.set(id, 0);
    tier.set(id, 0);
  }

  for (const edge of edges) {
    if (edge.relation !== "requires") continue;
    if (edge.source_topic_id === edge.target_topic_id) continue;
    if (!topicIdx.has(edge.source_topic_id) || !topicIdx.has(edge.target_topic_id)) continue;
    adj.get(edge.source_topic_id)!.push(edge.target_topic_id);
    indeg.set(edge.target_topic_id, (indeg.get(edge.target_topic_id) ?? 0) + 1);
    outdeg.set(edge.source_topic_id, (outdeg.get(edge.source_topic_id) ?? 0) + 1);
  }

  const remaining = new Set(topicIds);
  while (remaining.size > 0) {
    const ready = [...remaining]
      .filter((id) => (indeg.get(id) ?? 0) === 0)
      .sort((a, b) => (tier.get(a)! - tier.get(b)!) || (topicIdx.get(a)! - topicIdx.get(b)!));
    const current =
      ready[0] ??
      [...remaining].sort((a, b) => {
        const diffA = (outdeg.get(a) ?? 0) - (indeg.get(a) ?? 0);
        const diffB = (outdeg.get(b) ?? 0) - (indeg.get(b) ?? 0);
        return diffB - diffA || topicIdx.get(a)! - topicIdx.get(b)!;
      })[0]!;
    remaining.delete(current);
    const currentTier = tier.get(current) ?? 0;
    for (const next of adj.get(current) ?? []) {
      if (!remaining.has(next)) continue;
      indeg.set(next, Math.max(0, (indeg.get(next) ?? 0) - 1));
      tier.set(next, Math.max(tier.get(next) ?? 0, currentTier + 1));
    }
  }
  return tier;
}

function orderZoneIds(
  effectiveZoneIds: string[],
  edges: Edge[],
  topicZone: Map<string, string>,
): string[] {
  if (effectiveZoneIds.length <= 1) return effectiveZoneIds;
  const zoneOrder = new Map(effectiveZoneIds.map((id, i) => [id, i]));
  const adj = new Map<string, Set<string>>();
  const indeg = new Map<string, number>();
  const outdeg = new Map<string, number>();
  for (const zid of effectiveZoneIds) {
    adj.set(zid, new Set());
    indeg.set(zid, 0);
    outdeg.set(zid, 0);
  }
  for (const edge of edges) {
    if (edge.relation !== "requires") continue;
    const sz = topicZone.get(edge.source_topic_id);
    const tz = topicZone.get(edge.target_topic_id);
    if (!sz || !tz || sz === tz) continue;
    if (!adj.get(sz)!.has(tz)) {
      adj.get(sz)!.add(tz);
      indeg.set(tz, (indeg.get(tz) ?? 0) + 1);
      outdeg.set(sz, (outdeg.get(sz) ?? 0) + 1);
    }
  }
  const remaining = new Set(effectiveZoneIds);
  const ordered: string[] = [];
  while (remaining.size > 0) {
    const ready = [...remaining]
      .filter((id) => (indeg.get(id) ?? 0) === 0)
      .sort((a, b) => zoneOrder.get(a)! - zoneOrder.get(b)!);
    const curr =
      ready[0] ??
      [...remaining].sort((a, b) => {
        const diffA = (outdeg.get(a) ?? 0) - (indeg.get(a) ?? 0);
        const diffB = (outdeg.get(b) ?? 0) - (indeg.get(b) ?? 0);
        return diffB - diffA || zoneOrder.get(a)! - zoneOrder.get(b)!;
      })[0]!;
    remaining.delete(curr);
    ordered.push(curr);
    for (const nxt of adj.get(curr) ?? []) {
      if (remaining.has(nxt)) indeg.set(nxt, Math.max(0, (indeg.get(nxt) ?? 0) - 1));
    }
  }
  return ordered;
}

function distance(left: GraphPoint3D, right: GraphPoint3D): number {
  return Math.hypot(left.x - right.x, left.y - right.y, left.z - right.z);
}

export function buildGraph3DLayout(topics: Topic[], edges: Edge[], zones: Zone[]): Graph3DLayout {
  if (topics.length === 0) {
    return {
      positions: new Map(),
      center: { x: 0, y: 0, z: 0 },
      radius: 120,
      zoneCenters: new Map(),
      tiers: new Map(),
      tierElevations: [],
    };
  }

  const topicIndex = new Map(topics.map((topic, index) => [topic.id, index]));
  const topicZone = new Map<string, string>();
  for (const zone of zones) {
    for (const topicId of zone.topic_ids) {
      if (topicIndex.has(topicId) && !topicZone.has(topicId)) topicZone.set(topicId, zone.id);
    }
  }

  const rawZoneIds = [
    ...zones.filter((zone) => zone.topic_ids.some((topicId) => topicIndex.has(topicId))).map((zone) => zone.id),
    ...(topics.some((topic) => !topicZone.has(topic.id)) ? ["__unassigned__"] : []),
  ];
  const effectiveZoneIds = orderZoneIds(rawZoneIds, edges, topicZone);

  const tiers = computeGlobalTiers(topics, edges);
  const maxTier = Math.max(0, ...tiers.values());
  const midTier = maxTier / 2;
  const tierElevations: number[] = [];
  for (let t = 0; t <= maxTier; t += 1) {
    tierElevations.push((t - midTier) * TIER_SPACING);
  }

  const zoneMembers = new Map<string, string[]>();
  for (const zoneId of effectiveZoneIds) zoneMembers.set(zoneId, []);
  for (const topic of topics) {
    const zoneId = topicZone.get(topic.id) ?? "__unassigned__";
    zoneMembers.set(zoneId, [...(zoneMembers.get(zoneId) ?? []), topic.id]);
  }

  // Place zones on a non-overlapping horizontal X-Z grid so modules stay separated.
  const maxMembersInZone = Math.max(1, ...[...zoneMembers.values()].map((m) => m.length));
  const zoneFootprintRadius = 46 + Math.sqrt(maxMembersInZone) * 20;
  const cellSpacing = zoneFootprintRadius * 2.55;
  const cols = Math.max(1, Math.ceil(Math.sqrt(effectiveZoneIds.length)));
  const rows = Math.ceil(effectiveZoneIds.length / cols);

  const zoneCenters = new Map<string, GraphPoint3D>();
  effectiveZoneIds.forEach((zoneId, idx) => {
    const col = idx % cols;
    const row = Math.floor(idx / cols);
    const stagger = row % 2 === 1 && cols > 1 ? cellSpacing * 0.24 : 0;
    zoneCenters.set(zoneId, {
      x: (col - (cols - 1) / 2) * cellSpacing + stagger,
      y: 0,
      z: (row - (rows - 1) / 2) * cellSpacing,
    });
  });

  // Initial deterministic placement within each (zone, tier) slice on X-Z, Y strictly locked to tier.
  const positions = new Map<string, GraphPoint3D>();
  for (const zoneId of effectiveZoneIds) {
    const zCenter = zoneCenters.get(zoneId) ?? { x: 0, y: 0, z: 0 };
    const members = zoneMembers.get(zoneId) ?? [];
    const byTier = new Map<number, string[]>();
    for (const tid of members) {
      const t = tiers.get(tid) ?? 0;
      byTier.set(t, [...(byTier.get(t) ?? []), tid]);
    }
    for (const [tier, slice] of byTier) {
      slice.sort((a, b) => (topicIndex.get(a) ?? 0) - (topicIndex.get(b) ?? 0));
      const count = slice.length;
      const y = (tier - midTier) * TIER_SPACING;
      slice.forEach((tid, idx) => {
        if (count === 1) {
          const jitterAngle = ((hashString(tid) % 360) * Math.PI) / 180;
          positions.set(tid, {
            x: zCenter.x + Math.cos(jitterAngle) * 8,
            y,
            z: zCenter.z + Math.sin(jitterAngle) * 8,
          });
          return;
        }
        const angle = (idx / count) * Math.PI * 2 + ((hashString(zoneId) % 100) / 100) * 0.5;
        const ringRadius = Math.min(zoneFootprintRadius * 0.78, 28 + count * 9.5);
        positions.set(tid, {
          x: zCenter.x + Math.cos(angle) * ringRadius,
          y,
          z: zCenter.z + Math.sin(angle) * ringRadius,
        });
      });
    }
  }

  // Gentle X-Z only relaxation within zone bounds; Y remains strictly stratified.
  const velocities = new Map(topics.map((t) => [t.id, { x: 0, z: 0 }]));
  const intraEdges = edges
    .map((e) => ({
      edge: e,
      source: positions.get(e.source_topic_id),
      target: positions.get(e.target_topic_id),
      sameZone: (topicZone.get(e.source_topic_id) ?? "__unassigned__") === (topicZone.get(e.target_topic_id) ?? "__unassigned__"),
    }))
    .filter((item): item is { edge: Edge; source: GraphPoint3D; target: GraphPoint3D; sameZone: boolean } => Boolean(item.source && item.target && item.sameZone));

  const iterations = topics.length > 260 ? 36 : 56;
  const maxOffsetFromZone = zoneFootprintRadius * 0.88;
  for (let iter = 0; iter < iterations; iter += 1) {
    for (let i = 0; i < topics.length; i += 1) {
      const leftTopic = topics[i];
      const left = positions.get(leftTopic.id)!;
      const lv = velocities.get(leftTopic.id)!;
      const leftZone = topicZone.get(leftTopic.id) ?? "__unassigned__";
      for (let j = i + 1; j < topics.length; j += 1) {
        const rightTopic = topics[j];
        if ((topicZone.get(rightTopic.id) ?? "__unassigned__") !== leftZone) continue;
        const right = positions.get(rightTopic.id)!;
        const dx = left.x - right.x;
        const dz = left.z - right.z;
        const sameTier = tiers.get(leftTopic.id) === tiers.get(rightTopic.id);
        const dist = Math.hypot(dx, dz) || 0.01;
        const minClearance = sameTier ? 48 : 28;
        if (dist >= minClearance) continue;
        const push = ((minClearance - dist) / minClearance) * 1.4;
        const rv = velocities.get(rightTopic.id)!;
        lv.x += (dx / dist) * push;
        lv.z += (dz / dist) * push;
        rv.x -= (dx / dist) * push;
        rv.z -= (dz / dist) * push;
      }
    }

    for (const { source, target } of intraEdges) {
      const dx = target.x - source.x;
      const dz = target.z - source.z;
      const dist = Math.hypot(dx, dz) || 0.01;
      const targetDist = 42;
      const force = (dist - targetDist) * 0.018;
      const sv = velocities.get(
        topics.find((t) => positions.get(t.id) === source)?.id ?? "",
      );
      const tv = velocities.get(
        topics.find((t) => positions.get(t.id) === target)?.id ?? "",
      );
      if (sv && tv) {
        sv.x += (dx / dist) * force;
        sv.z += (dz / dist) * force;
        tv.x -= (dx / dist) * force;
        tv.z -= (dz / dist) * force;
      }
    }

    for (const topic of topics) {
      const pos = positions.get(topic.id)!;
      const vel = velocities.get(topic.id)!;
      const zCenter = zoneCenters.get(topicZone.get(topic.id) ?? "__unassigned__") ?? { x: 0, y: 0, z: 0 };
      vel.x = (vel.x + (zCenter.x - pos.x) * 0.025) * 0.72;
      vel.z = (vel.z + (zCenter.z - pos.z) * 0.025) * 0.72;
      pos.x += vel.x;
      pos.z += vel.z;
      const offsetX = pos.x - zCenter.x;
      const offsetZ = pos.z - zCenter.z;
      const offsetDist = Math.hypot(offsetX, offsetZ);
      if (offsetDist > maxOffsetFromZone) {
        const scale = maxOffsetFromZone / offsetDist;
        pos.x = zCenter.x + offsetX * scale;
        pos.z = zCenter.z + offsetZ * scale;
      }
    }
  }

  const center = topics.reduce<GraphPoint3D>(
    (sum, topic) => {
      const position = positions.get(topic.id)!;
      sum.x += position.x / topics.length;
      sum.y += position.y / topics.length;
      sum.z += position.z / topics.length;
      return sum;
    },
    { x: 0, y: 0, z: 0 },
  );
  let radius = 0;
  for (const position of positions.values()) radius = Math.max(radius, distance(position, center));

  return { positions, center, radius: Math.max(radius, 120), zoneCenters, tiers, tierElevations };
}
