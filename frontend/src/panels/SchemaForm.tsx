import type { NodeTypeDecl, WorkflowNodeData } from "../types/workflow";
import { Icon } from "../components/Icon";
import { PathField } from "./PathField";

export function SchemaForm({
  node,
  declaration,
  onChange,
  root,
  columnHints,
  variables,
  onCommentChange,
}: {
  node: WorkflowNodeData;
  declaration?: NodeTypeDecl;
  onChange: (params: Record<string, unknown>) => void;
  root: string;
  columnHints: string[];
  variables: string[];
  onCommentChange?: (comment: string) => void;
}) {
  const properties = declaration?.params_schema.properties ?? {};
  const required = new Set(
    (declaration?.params_schema.required as string[] | undefined) ?? [],
  );
  return (
    <form
      className="schema-form"
      onSubmit={(event) => {
        event.preventDefault();
      }}
    >
      <section className="form-section">
        <h3>参数</h3>
        {Object.entries(properties).map(([name, raw]) => {
          const field = raw as Record<string, unknown>;
          const value = node.params[name];
          const text = typeof value === "string" ? value : "";
          const label = `${name}${required.has(name) ? " *" : ""}`;
          const update = (next: unknown) => {
            onChange({ ...node.params, [name]: next });
          };
          return (
            <label
              className={`form-field${field.type === "boolean" ? " checkbox-field" : ""}`}
              key={name}
            >
              <span
                title={
                  typeof field.description === "string" ? field.description : ""
                }
              >
                {label}
              </span>
              <div className="field-control">
                {name === "code" ? (
                  <textarea
                    aria-label={label}
                    value={text}
                    onChange={(event) => {
                      update(event.target.value);
                    }}
                    onKeyDown={(event) => {
                      if (event.ctrlKey && event.key === "Enter") {
                        event.preventDefault();
                        window.dispatchEvent(
                          new CustomEvent("weft-execute-to"),
                        );
                      }
                    }}
                  />
                ) : name === "path" ? (
                  <PathField
                    label={label}
                    value={text}
                    root={root}
                    onChange={update}
                  />
                ) : name === "column" && columnHints.length > 0 ? (
                  <select
                    aria-label={label}
                    value={text}
                    onChange={(event) => {
                      update(event.target.value);
                    }}
                  >
                    <option value="">选择列</option>
                    {columnHints.map((column) => (
                      <option key={column} value={column}>
                        {column}
                      </option>
                    ))}
                  </select>
                ) : field.type === "boolean" ? (
                  <input
                    type="checkbox"
                    checked={Boolean(value)}
                    onChange={(event) => {
                      update(event.target.checked);
                    }}
                  />
                ) : field.type === "array" || field.type === "object" ? (
                  <textarea
                    value={JSON.stringify(
                      value ?? (field.type === "array" ? [] : {}),
                    )}
                    onChange={(event) => {
                      try {
                        update(JSON.parse(event.target.value));
                      } catch {
                        update(event.target.value);
                      }
                    }}
                  />
                ) : typeof value === "object" &&
                  value !== null &&
                  "$var" in value ? (
                  <>
                    <input
                      aria-label={label}
                      list={`${node.nodeId}-${name}-variables`}
                      value={String(value.$var)}
                      onChange={(event) => {
                        update({ $var: event.target.value });
                      }}
                    />
                    <datalist id={`${node.nodeId}-${name}-variables`}>
                      {variables.map((variable) => (
                        <option key={variable} value={variable} />
                      ))}
                    </datalist>
                  </>
                ) : (
                  <input
                    aria-label={label}
                    type={
                      field.type === "integer" || field.type === "number"
                        ? "number"
                        : "text"
                    }
                    value={
                      typeof value === "object" && value !== null
                        ? JSON.stringify(value)
                        : String(value)
                    }
                    onChange={(event) => {
                      update(
                        field.type === "integer" || field.type === "number"
                          ? event.target.valueAsNumber
                          : event.target.value,
                      );
                    }}
                  />
                )}
                <button
                  className="variable-button"
                  type="button"
                  title="绑定流变量"
                  onClick={() => {
                    update({ $var: name });
                  }}
                >
                  <Icon name="variable" />
                  <span>变量</span>
                </button>
              </div>
              {required.has(name) && (value === "" || value === undefined) && (
                <small className="field-error" role="alert">
                  必填
                </small>
              )}
            </label>
          );
        })}
        {Object.keys(properties).length === 0 && (
          <p className="form-empty">此节点没有可配置参数。</p>
        )}
      </section>
      {onCommentChange && (
        <section className="form-section comment-section">
          <h3>注释</h3>
          <label className="form-field">
            <span>节点注释</span>
            <textarea
              aria-label="节点注释"
              placeholder="记录这个节点的用途…"
              value={node.comment}
              onChange={(event) => {
                onCommentChange(event.target.value);
              }}
            />
            <small>注释会显示在节点上，并随工作流保存。</small>
          </label>
        </section>
      )}
    </form>
  );
}
