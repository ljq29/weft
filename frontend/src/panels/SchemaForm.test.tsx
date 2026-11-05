import { isValidElement } from "react";
import type { ReactElement, ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SchemaForm } from "./SchemaForm";
import type { NodeTypeDecl, WorkflowNodeData } from "../types/workflow";

const declaration: NodeTypeDecl = {
  type: "table.row_filter",
  name: "Row Filter",
  display_name: "行筛选",
  description: "Filter rows",
  category: "table",
  cache_policy: "pure",
  inputs: [],
  outputs: [],
  params_schema: {
    properties: {
      column: { type: "string", description: "Column" },
      operator: { type: "string", enum: ["=="] },
      value: { type: "string" },
    },
    required: ["column", "operator"],
  },
};

const node: WorkflowNodeData = {
  nodeId: "n_00000001",
  type: declaration.type,
  name: declaration.name,
  params: { column: "amount", operator: "==", value: "100" },
  inputs: [],
  outputs: [],
  comment: "",
  status: "configured",
};

type TestElement = ReactElement<Record<string, unknown>>;

function isArray(value: unknown): value is ReactNode[] {
  return Array.isArray(value);
}

function findElement(
  current: ReactNode,
  predicate: (element: TestElement) => boolean,
): TestElement | undefined {
  if (isArray(current)) {
    for (const child of current) {
      const match = findElement(child, predicate);
      if (match) {
        return match;
      }
    }
    return undefined;
  }
  if (!isValidElement(current)) {
    return undefined;
  }
  const element = current as TestElement;
  if (predicate(element)) {
    return element;
  }
  if (typeof element.type === "function") {
    const component = element.type as (
      props: Record<string, unknown>,
    ) => ReactNode;
    return findElement(component(element.props), predicate);
  }
  return findElement(element.props.children as ReactNode, predicate);
}

function byAria(current: ReactNode, label: string): TestElement {
  const match = findElement(
    current,
    (element) => element.props["aria-label"] === label,
  );
  if (!match) {
    throw new Error(`Control not found: ${label}`);
  }
  return match;
}

function changeText(
  control: TestElement,
  value: string,
  valueAsNumber?: number,
) {
  const onChange = control.props.onChange as
    | ((event: { target: { value: string; valueAsNumber?: number } }) => void)
    | undefined;
  if (!onChange) {
    throw new Error("Control has no change handler");
  }
  onChange({ target: { value, valueAsNumber } });
}

function click(control: TestElement) {
  const onClick = control.props.onClick as (() => void) | undefined;
  if (!onClick) {
    throw new Error("Control has no click handler");
  }
  onClick();
}

function formWithSchema(
  paramsSchema: Record<string, unknown>,
  params: Record<string, unknown>,
  onChange: (params: Record<string, unknown>) => void = () => undefined,
) {
  return (
    <SchemaForm
      node={{ ...node, params }}
      declaration={{ ...declaration, params_schema: paramsSchema }}
      onChange={onChange}
      root="C:/flow"
      columnHints={["amount", "region"]}
      variables={["target_wb"]}
    />
  );
}

describe("T2.2 schema form", () => {
  it("US-DES-04/AC-1,3: generates row filter fields and required indicators", () => {
    const html = renderToStaticMarkup(
      <SchemaForm
        node={node}
        declaration={declaration}
        onChange={() => undefined}
        root="C:/flow"
        columnHints={["amount", "region"]}
        variables={["target_wb"]}
      />,
    );
    expect(html).toContain("column");
    expect(html).toContain("operator");
    expect(html).toContain("value");
    expect(html).toContain("amount");
    expect(html).toContain("region");
    expect(html).toContain('<select aria-label="operator *"');
  });

  it("US-DES-06/AC-1: variable binding lists available variables", () => {
    const bound = { ...node, params: { value: { $var: "target_wb" } } };
    const html = renderToStaticMarkup(
      <SchemaForm
        node={bound}
        declaration={declaration}
        onChange={() => undefined}
        root="C:/flow"
        columnHints={[]}
        variables={["target_wb"]}
      />,
    );
    expect(html).toContain("target_wb");
    expect(html).toContain("datalist");
  });

  it("US-DES-04/AC-1: enum controls preserve the selected value type", () => {
    let next: Record<string, unknown> = {};
    const form = formWithSchema(
      { properties: { operator: { type: "number", enum: [1, 2] } } },
      { operator: 1 },
      (params) => {
        next = params;
      },
    );
    const select = byAria(form, "operator");
    expect(select.type).toBe("select");
    changeText(select, "1");
    expect(next).toEqual({ operator: 2 });
  });

  it("US-DES-04/AC-1,3: renders nested object groups and nested required errors", () => {
    const html = renderToStaticMarkup(
      formWithSchema(
        {
          properties: {
            settings: {
              type: "object",
              properties: {
                enabled: { type: "boolean" },
                retries: { type: "integer" },
              },
              required: ["retries"],
            },
          },
        },
        { settings: { enabled: true, retries: "" } },
      ),
    );
    expect(html).toContain('<fieldset class="form-field schema-object">');
    expect(html).toContain('aria-label="settings.enabled"');
    expect(html).toContain('aria-label="settings.retries *"');
    expect(html).toContain("必填");
  });

  it("US-DES-04/AC-2: nested edits update only the targeted object property", () => {
    let next: Record<string, unknown> = {};
    const form = formWithSchema(
      {
        properties: {
          settings: {
            type: "object",
            properties: { retries: { type: "integer" } },
            required: ["retries"],
          },
        },
      },
      { settings: { retries: 1, enabled: true }, untouched: "yes" },
      (params) => {
        next = params;
      },
    );
    changeText(byAria(form, "settings.retries *"), "4", 4);
    expect(next).toEqual({
      settings: { retries: 4, enabled: true },
      untouched: "yes",
    });
  });

  it("US-DES-04/AC-1,2: array records support editing, adding and deleting", () => {
    const schema = {
      properties: {
        rules: {
          type: "array",
          items: {
            type: "object",
            properties: {
              condition: { type: "string" },
              value: { type: "string" },
            },
          },
        },
      },
    };
    const params = {
      rules: [
        { condition: "a", value: "1" },
        { condition: "b", value: "2" },
      ],
      untouched: true,
    };
    let next: Record<string, unknown> = {};
    const capture = (updated: Record<string, unknown>) => {
      next = updated;
    };

    changeText(
      byAria(formWithSchema(schema, params, capture), "rules[0].condition"),
      "x",
    );
    expect(next).toEqual({
      rules: [
        { condition: "x", value: "1" },
        { condition: "b", value: "2" },
      ],
      untouched: true,
    });

    click(byAria(formWithSchema(schema, params, capture), "添加rules项"));
    expect(next).toEqual({
      rules: [...params.rules, {}],
      untouched: true,
    });

    click(byAria(formWithSchema(schema, params, capture), "删除rules第1项"));
    expect(next).toEqual({ rules: [params.rules[1]], untouched: true });
  });

  it("US-DES-06/AC-1,2: nested array fields retain variable binding", () => {
    let next: Record<string, unknown> = {};
    const form = formWithSchema(
      {
        properties: {
          rules: {
            type: "array",
            items: {
              type: "object",
              properties: { condition: { type: "string" } },
            },
          },
        },
      },
      { rules: [{ condition: "a" }] },
      (params) => {
        next = params;
      },
    );
    click(byAria(form, "绑定rules[0].condition到流变量"));
    expect(next).toEqual({ rules: [{ condition: { $var: "condition" } }] });
  });

  it("US-DES-04/AC-1,2: object mappings support key and value editing", () => {
    const schema = {
      properties: {
        mapping: {
          type: "object",
          additionalProperties: { type: "string" },
        },
      },
    };
    const params = { mapping: { old: "new", keep: "yes" }, untouched: true };
    let next: Record<string, unknown> = {};
    const capture = (updated: Record<string, unknown>) => {
      next = updated;
    };

    changeText(
      byAria(formWithSchema(schema, params, capture), "mapping.old"),
      "updated",
    );
    expect(next).toEqual({
      mapping: { old: "updated", keep: "yes" },
      untouched: true,
    });

    changeText(
      byAria(formWithSchema(schema, params, capture), "mapping键1"),
      "renamed",
    );
    expect(next).toEqual({
      mapping: { renamed: "new", keep: "yes" },
      untouched: true,
    });

    click(byAria(formWithSchema(schema, params, capture), "添加mapping键值"));
    expect(next).toEqual({
      mapping: { old: "new", keep: "yes", key_1: "" },
      untouched: true,
    });

    click(byAria(formWithSchema(schema, params, capture), "删除mapping键old"));
    expect(next).toEqual({ mapping: { keep: "yes" }, untouched: true });
  });

  it("US-DES-06/AC-1,2: bound structured values stay in variable mode", () => {
    let next: Record<string, unknown> = {};
    const form = formWithSchema(
      {
        properties: {
          schedules: {
            type: "array",
            items: { type: "object", properties: { cron: { type: "string" } } },
          },
        },
      },
      { schedules: { $var: "target_wb" } },
      (params) => {
        next = params;
      },
    );
    expect(
      findElement(
        form,
        (element) => element.props["aria-label"] === "添加schedules项",
      ),
    ).toBeUndefined();
    changeText(byAria(form, "schedules"), "another_variable");
    expect(next).toEqual({ schedules: { $var: "another_variable" } });
  });

  it("US-DES-04/AC-1: arrays without item schemas retain JSON editing", () => {
    let next: Record<string, unknown> = {};
    const form = formWithSchema(
      { properties: { watches: { type: "array" } } },
      { watches: [{ path: "data" }] },
      (params) => {
        next = params;
      },
    );
    const textarea = byAria(form, "watches");
    expect(textarea.type).toBe("textarea");
    changeText(textarea, '[{"path":"other"}]');
    expect(next).toEqual({ watches: [{ path: "other" }] });
  });

  it("US-DES-04/AC-1,5: code and nested path fields keep their specialized controls", () => {
    const html = renderToStaticMarkup(
      formWithSchema(
        {
          properties: {
            code: { type: "string" },
            target: {
              type: "object",
              properties: { path: { type: "string" } },
            },
          },
        },
        { code: "return 1", target: { path: "data/input.csv" } },
      ),
    );
    expect(html).toContain('<textarea aria-label="code"');
    expect(html).toContain('aria-label="target.path"');
    expect(html).toContain("选择路径");
  });
});
