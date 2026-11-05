import type { NodeTypeDecl, WorkflowNodeData } from "../types/workflow";
import { SchemaField } from "./SchemaField";
import type { ParameterSchema } from "./SchemaField";

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
  const rawProperties = declaration?.params_schema.properties;
  const properties: Record<string, ParameterSchema> =
    typeof rawProperties === "object" &&
    rawProperties !== null &&
    !Array.isArray(rawProperties)
      ? (rawProperties as Record<string, ParameterSchema>)
      : {};
  const rawRequired = declaration?.params_schema.required;
  const required = new Set(
    Array.isArray(rawRequired)
      ? rawRequired.filter((name): name is string => typeof name === "string")
      : [],
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
        {Object.entries(properties).map(([name, schema]) => (
          <SchemaField
            key={name}
            nodeId={node.nodeId}
            name={name}
            schema={schema}
            value={node.params[name]}
            required={required.has(name)}
            root={root}
            columnHints={columnHints}
            variables={variables}
            onChange={(next) => {
              onChange({ ...node.params, [name]: next });
            }}
          />
        ))}
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
