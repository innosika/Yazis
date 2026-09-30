import { afterEach, describe, expect, it } from "vitest";
import { applyTheme, resolveTheme } from "./theme";

describe("theme", () => {
  afterEach(() => applyTheme("system"));

  it("sets and removes the data-theme attribute", () => {
    applyTheme("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(localStorage.getItem("irs.theme")).toBe("dark");
    applyTheme("system");
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
    expect(localStorage.getItem("irs.theme")).toBeNull();
  });

  it("resolves an explicit preference as itself", () => {
    expect(resolveTheme("light")).toBe("light");
    expect(resolveTheme("dark")).toBe("dark");
    expect(["light", "dark"]).toContain(resolveTheme("system"));
  });
});
