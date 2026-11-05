import type { ReactNode } from "react";
import { Icon } from "../components/Icon";
import { PathField } from "./PathField";

export type ParameterSchema = Record<string, unknown>;

interface SchemaFieldProps {
  nodeId: string;
  name: string;
  fieldName?: string;
  schema: ParameterSchema;
  value: unknown;
  required?: boolean;
  onChange: (value: unknown) => void;
  root: string;
  columnHints: string[];
  variables: string[];
}

interface StructuredFieldProps extends SchemaFieldProps {
  label: string;
  variableButton: ReactNode;
}

function isArray(value: unknown): value is unknown[] {
  return Array.isArray(value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !isArray(value);
}

function isVariableBinding(
  value: unknown,
): value is Record<string, unknown> & { $var: unknown } {
  return isRecord(value) && "$var" in value;
}

function propertiesOf(
  schema: ParameterSchema,
): Record<string, ParameterSchema> {
  if (!isRecord(schema.properties)) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(schema.properties).filter(
      (entry): entry is [string, ParameterSchema] => isRecord(entry[1]),
    ),
  );
}

function requiredOf(schema: ParameterSchema): Set<string> {
  return new Set(
    isArray(schema.required)
      ? schema.required.filter(
          (name): name is string => typeof name === "string",
        )
      : [],
  );
}

function defaultFor(schema: ParameterSchema): unknown {
  if (schema.default !== undefined) {
    return isRecord(schema.default) || isArray(schema.default)
      ? (JSON.parse(JSON.stringify(schema.default)) as unknown)
      : schema.default;
  }
  switch (schema.type) {
    case "object": {
      const defaults: Record<string, unknown> = {};
      for (const [name, property] of Object.entries(propertiesOf(schema))) {
        if (property.default !== undefined) {
          defaults[name] = defaultFor(property);
        }
      }
      return defaults;
    }
    case "array":
      return [];
    case "boolean":
      return false;
    case "integer":
    case "number":
      return 0;
    default:
      return "";
  }
}

function scalarText(value: unknown): string {
  if (value === undefined || value === null) {
    return "";
  }
  if (typeof value === "string") {
    return value;
  }
  if (
    typeof value === "number" ||
    typeof value === "boolean" ||
    typeof value === "bigint" ||
    typeof value === "symbol"
  ) {
    return String(value);
  }
  const serialized: unknown = JSON.stringify(value);
  return typeof serialized === "string" ? serialized : "";
}

function FieldError({ show }: { show: boolean }) {
  return show ? (
    <small className="field-error" role="alert">
      必填
    </small>
  ) : null;
}

function ObjectField(props: StructuredFieldProps) {
  const { name, schema, value, required, onChange, label, variableButton } =
    props;
  const record = isRecord(value) ? value : {};
  const properties = propertiesOf(schema);
  const requiredProperties = requiredOf(schema);
  const propertyNames = new Set(Object.keys(properties));
  const hasProperties = propertyNames.size > 0;
  const allowAdditional =
    !hasProperties ||
    (schema.additionalProperties !== undefined &&
      schema.additionalProperties !== false);
  const additionalSchema = isRecord(schema.additionalProperties)
    ? schema.additionalProperties
    : {};

  return (
    <fieldset className="form-field schema-object">
      <legend
        title={typeof schema.description === "string" ? schema.description : ""}
      >
        {label}
      </legend>
      <div className="field-control">
        <div className="schema-object-fields">
          {Object.entries(properties).map(([propertyName, propertySchema]) => (
            <SchemaField
              {...props}
              key={propertyName}
              name={`${name}.${propertyName}`}
              fieldName={propertyName}
              schema={propertySchema}
              value={record[propertyName]}
              required={requiredProperties.has(propertyName)}
              onChange={(next) => {
                onChange({ ...record, [propertyName]: next });
              }}
            />
          ))}
          {allowAdditional && (
            <KeyValueEntries
              {...props}
              value={record}
              fixedProperties={propertyNames}
              valueSchema={additionalSchema}
              onChange={onChange}
            />
          )}
          {!hasProperties && !allowAdditional && (
            <p className="form-empty">此对象没有可配置字段。</p>
          )}
        </div>
        {variableButton}
      </div>
      <FieldError
        show={Boolean(required) && (value === "" || value === undefined)}
      />
    </fieldset>
  );
}

function ArrayField(
  props: StructuredFieldProps & { itemSchema: ParameterSchema },
) {
  const {
    name,
    fieldName,
    value,
    required,
    onChange,
    label,
    variableButton,
    itemSchema,
  } = props;
  const items = isArray(value) ? value : [];

  return (
    <div className="form-field schema-array">
      <span
        title={
          typeof props.schema.description === "string"
            ? props.schema.description
            : ""
        }
      >
        {label}
      </span>
      <div className="field-control">
        <div className="schema-array-items">
          {items.map((item, index) => (
            <div className="schema-array-item" key={index}>
              <SchemaField
                {...props}
                name={`${name}[${String(index)}]`}
                fieldName={fieldName}
                schema={itemSchema}
                value={item}
                required={false}
                onChange={(next) => {
                  onChange(
                    items.map((current, i) => (i === index ? next : current)),
                  );
                }}
              />
              <button
                className="button ghost"
                type="button"
                aria-label={`删除${label}第${String(index + 1)}项`}
                onClick={() => {
                  onChange(items.filter((_, i) => i !== index));
                }}
              >
                <Icon name="trash" />
                删除
              </button>
            </div>
          ))}
          <button
            className="button ghost"
            type="button"
            aria-label={`添加${label}项`}
            onClick={() => {
              onChange([...items, defaultFor(itemSchema)]);
            }}
          >
            <Icon name="plus" />
            添加项
          </button>
        </div>
        {variableButton}
      </div>
      <FieldError
        show={Boolean(required) && (value === "" || value === undefined)}
      />
    </div>
  );
}

function KeyValueEntries({
  value,
  fixedProperties,
  valueSchema,
  onChange,
  ...props
}: StructuredFieldProps & {
  value: Record<string, unknown>;
  fixedProperties: Set<string>;
  valueSchema: ParameterSchema;
}) {
  const entries = Object.entries(value).filter(
    ([key]) => !fixedProperties.has(key),
  );
  const fixedEntries = Object.entries(value).filter(([key]) =>
    fixedProperties.has(key),
  );
  const updateEntries = (nextEntries: [string, unknown][]) => {
    onChange(Object.fromEntries([...fixedEntries, ...nextEntries]));
  };

  return (
    <div className="schema-map">
      {fixedProperties.size > 0 && (
        <span className="schema-map-title">自定义字段</span>
      )}
      {entries.map(([key, item], index) => (
        <div className="schema-map-row" key={`${key}:${String(index)}`}>
          <input
            aria-label={`${props.label}键${String(index + 1)}`}
            value={key}
            onChange={(event) => {
              const nextKey = event.target.value;
              if (
                nextKey !== key &&
                (fixedProperties.has(nextKey) ||
                  entries.some(
                    ([entryKey], i) => i !== index && entryKey === nextKey,
                  ))
              ) {
                return;
              }
              updateEntries(
                entries.map(([entryKey, entryValue], i) =>
                  i === index ? [nextKey, entryValue] : [entryKey, entryValue],
                ),
              );
            }}
          />
          <div className="schema-map-value">
            <SchemaField
              {...props}
              name={`${props.name}.${key}`}
              fieldName={key}
              schema={valueSchema}
              value={item}
              required={false}
              onChange={(next) => {
                updateEntries(
                  entries.map(([entryKey, entryValue], i) =>
                    i === index ? [entryKey, next] : [entryKey, entryValue],
                  ),
                );
              }}
            />
          </div>
          <button
            className="button ghost"
            type="button"
            aria-label={`删除${props.label}键${key}`}
            onClick={() => {
              updateEntries(entries.filter((_, i) => i !== index));
            }}
          >
            <Icon name="trash" />
            删除
          </button>
        </div>
      ))}
      <button
        className="button ghost"
        type="button"
        aria-label={`添加${props.label}键值`}
        onClick={() => {
          let suffix = 1;
          while (Object.hasOwn(value, `key_${String(suffix)}`)) {
            suffix += 1;
          }
          updateEntries([
            ...entries,
            [`key_${String(suffix)}`, defaultFor(valueSchema)],
          ]);
        }}
      >
        <Icon name="plus" />
        添加键值
      </button>
    </div>
  );
}

export function SchemaField(props: SchemaFieldProps) {
  const {
    nodeId,
    name,
    fieldName = name,
    schema,
    value,
    required = false,
    onChange,
    root,
    columnHints,
    variables,
  } = props;
  const label = `${name}${required ? " *" : ""}`;
  const description =
    typeof schema.description === "string" ? schema.description : "";
  const variableButton = (
    <button
      className="variable-button"
      type="button"
      title="绑定流变量"
      aria-label={`绑定${label}到流变量`}
      onClick={() => {
        onChange({ $var: fieldName });
      }}
    >
      <Icon name="variable" />
      <span>变量</span>
    </button>
  );

  if (isVariableBinding(value)) {
    const listId = `${nodeId}-${encodeURIComponent(name)}-variables`;
    return (
      <label className="form-field">
        <span title={description}>{label}</span>
        <div className="field-control">
          <input
            aria-label={label}
            list={listId}
            value={scalarText(value.$var)}
            onChange={(event) => {
              onChange({ $var: event.target.value });
            }}
          />
          <datalist id={listId}>
            {variables.map((variable) => (
              <option key={variable} value={variable} />
            ))}
          </datalist>
          {variableButton}
        </div>
      </label>
    );
  }

  if (schema.type === "object") {
    return (
      <ObjectField {...props} label={label} variableButton={variableButton} />
    );
  }

  if (schema.type === "array" && isRecord(schema.items)) {
    return (
      <ArrayField
        {...props}
        label={label}
        variableButton={variableButton}
        itemSchema={schema.items}
      />
    );
  }

  let control: ReactNode;
  if (fieldName === "code") {
    control = (
      <textarea
        aria-label={label}
        value={scalarText(value)}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        onKeyDown={(event) => {
          if (event.ctrlKey && event.key === "Enter") {
            event.preventDefault();
            window.dispatchEvent(new CustomEvent("weft-execute-to"));
          }
        }}
      />
    );
  } else if (fieldName === "path") {
    control = (
      <PathField
        label={label}
        value={scalarText(value)}
        root={root}
        onChange={onChange}
      />
    );
  } else if (fieldName === "column" && columnHints.length > 0) {
    control = (
      <select
        aria-label={label}
        value={scalarText(value)}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      >
        <option value="">选择列</option>
        {columnHints.map((column) => (
          <option key={column} value={column}>
            {column}
          </option>
        ))}
      </select>
    );
  } else if (isArray(schema.enum)) {
    const options = schema.enum;
    const selected = options.findIndex((option) => Object.is(option, value));
    control = (
      <select
        aria-label={label}
        value={selected >= 0 ? String(selected) : ""}
        onChange={(event) => {
          onChange(
            event.target.value === ""
              ? ""
              : options[Number(event.target.value)],
          );
        }}
      >
        <option value="">请选择</option>
        {options.map((option, index) => (
          <option
            key={`${scalarText(option)}:${String(index)}`}
            value={String(index)}
          >
            {scalarText(option)}
          </option>
        ))}
      </select>
    );
  } else if (schema.type === "boolean") {
    control = (
      <input
        aria-label={label}
        type="checkbox"
        checked={Boolean(value)}
        onChange={(event) => {
          onChange(event.target.checked);
        }}
      />
    );
  } else if (schema.type === "array" || schema.type === "object") {
    control = (
      <textarea
        aria-label={label}
        value={JSON.stringify(value ?? (schema.type === "array" ? [] : {}))}
        onChange={(event) => {
          try {
            onChange(JSON.parse(event.target.value) as unknown);
          } catch {
            onChange(event.target.value);
          }
        }}
      />
    );
  } else {
    const isNumber = schema.type === "integer" || schema.type === "number";
    control = (
      <input
        aria-label={label}
        type={isNumber ? "number" : "text"}
        value={scalarText(value)}
        onChange={(event) => {
          onChange(
            isNumber
              ? event.target.value === ""
                ? ""
                : event.target.valueAsNumber
              : event.target.value,
          );
        }}
      />
    );
  }

  return (
    <label
      className={`form-field${schema.type === "boolean" ? " checkbox-field" : ""}`}
    >
      <span title={description}>{label}</span>
      <div className="field-control">
        {control}
        {variableButton}
      </div>
      <FieldError show={required && (value === "" || value === undefined)} />
    </label>
  );
}
