import { beforeEach, describe, expect, it } from "vitest";

import {
  CANVAS_STYLE_STORAGE_KEY,
  DEFAULT_CANVAS_STYLE,
  normalizeCanvasStyle,
  readStoredCanvasStyle,
  writeStoredCanvasStyle,
} from "./canvasStyle";

beforeEach(() => localStorage.clear());

describe("canvasStyle", () => {
  it("clamps out-of-range values and falls back on invalid fields", () => {
    expect(
      normalizeCanvasStyle({
        labelFontSize: 99,
        labelOpacity: -1,
        edgeOpacity: 2,
        edgeWidth: 0.1,
        showZoneOutlines: "yes",
      }),
    ).toEqual({
      labelFontSize: 18,
      labelOpacity: 0.3,
      edgeOpacity: 0.65,
      edgeWidth: 0.8,
      showZoneOutlines: true,
    });
  });

  it("persists and reloads normalized style preferences", () => {
    const custom = {
      labelFontSize: 15,
      labelOpacity: 0.95,
      edgeOpacity: 0.36,
      edgeWidth: 2,
      showZoneOutlines: false,
    };
    writeStoredCanvasStyle(custom);
    expect(readStoredCanvasStyle()).toEqual(custom);
    localStorage.setItem(CANVAS_STYLE_STORAGE_KEY, "{bad-json");
    expect(readStoredCanvasStyle()).toEqual(DEFAULT_CANVAS_STYLE);
  });
});
