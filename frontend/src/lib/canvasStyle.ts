export type CanvasStylePreferences = {
  labelFontSize: number;
  labelOpacity: number;
  edgeOpacity: number;
  edgeWidth: number;
  showZoneOutlines: boolean;
};

export const CANVAS_STYLE_STORAGE_KEY = "knowledge_graph_canvas_style_v1";

export const DEFAULT_CANVAS_STYLE: CanvasStylePreferences = {
  labelFontSize: 12,
  labelOpacity: 0.85,
  edgeOpacity: 0.22,
  edgeWidth: 1.2,
  showZoneOutlines: true,
};

function clampNumber(value: unknown, min: number, max: number, fallback: number): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return fallback;
  return Math.min(max, Math.max(min, value));
}

export function normalizeCanvasStyle(raw: unknown): CanvasStylePreferences {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return { ...DEFAULT_CANVAS_STYLE };
  const record = raw as Record<string, unknown>;
  return {
    labelFontSize: Math.round(clampNumber(record.labelFontSize, 10, 18, DEFAULT_CANVAS_STYLE.labelFontSize)),
    labelOpacity: Number(clampNumber(record.labelOpacity, 0.3, 1, DEFAULT_CANVAS_STYLE.labelOpacity).toFixed(2)),
    edgeOpacity: Number(clampNumber(record.edgeOpacity, 0.06, 0.65, DEFAULT_CANVAS_STYLE.edgeOpacity).toFixed(2)),
    edgeWidth: Number(clampNumber(record.edgeWidth, 0.8, 3, DEFAULT_CANVAS_STYLE.edgeWidth).toFixed(1)),
    showZoneOutlines: typeof record.showZoneOutlines === "boolean" ? record.showZoneOutlines : DEFAULT_CANVAS_STYLE.showZoneOutlines,
  };
}

export function readStoredCanvasStyle(): CanvasStylePreferences {
  try {
    const raw = localStorage.getItem(CANVAS_STYLE_STORAGE_KEY);
    if (!raw) return { ...DEFAULT_CANVAS_STYLE };
    return normalizeCanvasStyle(JSON.parse(raw));
  } catch {
    return { ...DEFAULT_CANVAS_STYLE };
  }
}

export function writeStoredCanvasStyle(style: CanvasStylePreferences): void {
  try {
    localStorage.setItem(CANVAS_STYLE_STORAGE_KEY, JSON.stringify(normalizeCanvasStyle(style)));
  } catch {
    // Storage is optional.
  }
}
