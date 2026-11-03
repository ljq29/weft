import type { NodeTypeDecl, WorkflowNodeData } from "../types/workflow";
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
      <h2>{node.name}</h2>
      {Object.entries(properties).map(([name, raw]) => {
        const field = raw as Record<string, unknown>;
        const value = node.params[name];
        const text = typeof value === "string" ? value : "";
        const label = `${name}${required.has(name) ? " *" : ""}`;
        const update = (next: unknown) => {
          onChange({ ...node.params, [name]: next });
        };
        return (
          <label key={name}>
            <span
              title={
                typeof field.description === "string" ? field.description : ""
              }
            >
              {label}
            </span>
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
                    window.dispatchEvent(new CustomEvent("weft-execute-to"));
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
            {required.has(name) && (value === "" || value === undefined) && (
              <small role="alert">必填</small>
            )}
            <button
              type="button"
              title="绑定流变量"
              onClick={() => {
                update({ $var: name });
              }}
            >
              变量
            </button>
          </label>
        );
      })}
      {onCommentChange && (
        <label>
          <span>注释</span>
          <textarea
            aria-label="节点注释"
            value={node.comment}
            onChange={(event) => {
              onCommentChange(event.target.value);
            }}
          />
        </label>
      )}
    </form>
  );
}
