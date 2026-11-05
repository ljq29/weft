import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ConfirmDialog, Dialog, FormDialog } from "./Dialog";

describe("reusable dialogs", () => {
  it("US-DES-07/AC-2: exposes an accessible labelled modal and error", () => {
    const html = renderToStaticMarkup(
      <Dialog title="打开工作流" error="目录不存在" onClose={() => undefined}>
        <p>选择工作流目录</p>
      </Dialog>,
    );
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-modal="true"');
    expect(html).toContain("aria-labelledby=");
    expect(html).toContain("打开工作流");
    expect(html).toContain('role="alert"');
    expect(html).toContain("目录不存在");
  });

  it("US-PKG-06/AC-1: gives confirmations explicit choices", () => {
    const html = renderToStaticMarkup(
      <ConfirmDialog
        title="外部资源缺失"
        message="仍要运行？"
        confirmLabel="仍要运行"
        onConfirm={() => undefined}
        onCancel={() => undefined}
      />,
    );
    expect(html).toContain("仍要运行");
    expect(html).toContain("取消");
  });

  it("US-PKG-04/AC-1: renders labelled fields instead of native prompts", () => {
    const html = renderToStaticMarkup(
      <FormDialog
        title="导入工作流"
        fields={[
          { name: "zipPath", label: "工作流 zip 路径" },
          {
            name: "destDir",
            label: "导入目标父目录",
            defaultValue: "C:/flows",
          },
        ]}
        submitLabel="导入"
        onSubmit={() => undefined}
        onCancel={() => undefined}
      />,
    );
    expect(html).toContain('aria-label="工作流 zip 路径"');
    expect(html).toContain('value="C:/flows"');
    expect(html).toContain("导入");
  });
});
