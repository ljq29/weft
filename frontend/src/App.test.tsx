import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { App } from "./App";

describe("T0.1 frontend skeleton", () => {
  it("renders the product and all foundation cards", () => {
    const html = renderToStaticMarkup(<App />);
    expect(html).toContain("Weft");
    expect(html).toContain("Python workspace");
    expect(html).toContain("Frontend toolchain");
    expect(html).toContain("Verification");
  });
});
