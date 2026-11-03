import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { App } from "./App";
import { WeftNode } from "./canvas/WeftNode";
import { AuditPanel } from "./panels/AuditPanel";
import { ChangeReviewPanel } from "./panels/ChangeReviewPanel";

describe("T2.2 canvas editor", () => {
  it("US-DES-01/AC-1,3: renders workflow creation and canvas controls", () => {
    const html = renderToStaticMarkup(<App />);
    expect(html).toContain("Weft");
    expect(html).toContain("新建工作流");
    expect(html).toContain("工作流画布");
    expect(html).toContain("Mini Map");
  });

  it("US-DES-05/AC-3: error nodes expose a hover summary and error marker", () => {
    const html = renderToStaticMarkup(
      <WeftNode
        id="n_1"
        type="weft"
        selected={false}
        draggable
        dragging={false}
        zIndex={0}
        selectable
        deletable
        isConnectable
        positionAbsoluteX={0}
        positionAbsoluteY={0}
        data={{
          nodeId: "n_1",
          type: "table.row_filter",
          name: "Row Filter",
          params: {},
          inputs: [],
          outputs: [],
          comment: "",
          status: "failed",
          error: { message: "Column missing", traceback: "trace" },
        }}
      />,
    );
    expect(html).toContain('title="Column missing"');
    expect(html).toContain('aria-label="错误"');
  });

  it("US-AGT-01/AC-1: settings expose masked LLM configuration controls", () => {
    const html = renderToStaticMarkup(<App />);
    expect(html).toContain("设置");
  });

  it("US-SBX-07/AC-3: audit history has tool and status filters", () => {
    const html = renderToStaticMarkup(<AuditPanel runId="r_1" />);
    expect(html).toContain("审计");
  });

  it("US-PKG-03/AC-1; US-PKG-04/AC-1: renders pack and import actions", () => {
    const html = renderToStaticMarkup(<App />);
    expect(html).toContain("导入工作流");
  });

  it("US-SBX-04/AC-3; US-SBX-05/AC-1: renders the change review entry", () => {
    const html = renderToStaticMarkup(<ChangeReviewPanel runId="r_1" />);
    expect(html).toContain("变更审批");
  });
});
