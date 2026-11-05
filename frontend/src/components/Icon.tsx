import type { ReactNode } from "react";

export type IconName =
  | "agent"
  | "arrow"
  | "check"
  | "chevron"
  | "close"
  | "code"
  | "copy"
  | "down"
  | "excel"
  | "eye"
  | "file"
  | "filter"
  | "flow"
  | "folder"
  | "grid"
  | "group"
  | "history"
  | "import"
  | "info"
  | "more"
  | "open"
  | "package"
  | "play"
  | "plus"
  | "save"
  | "search"
  | "send"
  | "settings"
  | "shield"
  | "stop"
  | "table"
  | "terminal"
  | "trash"
  | "trigger"
  | "variable"
  | "warn";

const paths: Record<IconName, ReactNode> = {
  agent: (
    <>
      <path d="M12 3v3M5.6 5.6l2.1 2.1M3 12h3M18 12h3M7 21h10a2 2 0 0 0 2-2v-6a7 7 0 0 0-14 0v6a2 2 0 0 0 2 2Z" />
      <circle cx="9" cy="13" r=".8" />
      <circle cx="15" cy="13" r=".8" />
    </>
  ),
  arrow: <path d="M5 12h14m-5-5 5 5-5 5" />,
  check: <path d="m5 12 4 4L19 6" />,
  chevron: <path d="m9 6 6 6-6 6" />,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  code: <path d="m8 6-6 6 6 6m8-12 6 6-6 6M14 3l-4 18" />,
  copy: (
    <>
      <rect x="8" y="8" width="12" height="12" rx="2" />
      <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" />
    </>
  ),
  down: <path d="m6 9 6 6 6-6" />,
  excel: (
    <>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M3 9h18M9 9v12m5-9 4 5m0-5-4 5" />
    </>
  ),
  eye: (
    <>
      <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z" />
      <circle cx="12" cy="12" r="2.5" />
    </>
  ),
  file: (
    <>
      <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z" />
      <path d="M14 3v6h6M8 13h8m-8 4h5" />
    </>
  ),
  filter: <path d="M4 5h16l-6 7v6l-4 2v-8Z" />,
  flow: (
    <>
      <rect x="3" y="3" width="6" height="6" rx="1.5" />
      <rect x="15" y="15" width="6" height="6" rx="1.5" />
      <path d="M9 6h4a4 4 0 0 1 4 4v5m-3-3 3 3 3-3" />
    </>
  ),
  folder: (
    <path d="M3 6a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
  ),
  grid: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </>
  ),
  group: (
    <>
      <path d="M4 5h16M4 12h16M4 19h16" />
      <circle cx="8" cy="5" r="2" />
      <circle cx="15" cy="12" r="2" />
      <circle cx="10" cy="19" r="2" />
    </>
  ),
  history: (
    <>
      <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
      <path d="M3 3v5h5m4-1v5l3 2" />
    </>
  ),
  import: (
    <path d="M12 3v12m-4-4 4 4 4-4M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" />
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v6m0-10h.01" />
    </>
  ),
  more: (
    <>
      <circle cx="5" cy="12" r=".8" />
      <circle cx="12" cy="12" r=".8" />
      <circle cx="19" cy="12" r=".8" />
    </>
  ),
  open: (
    <>
      <path d="M3 7a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v2" />
      <path d="M3 7v11a2 2 0 0 0 2 2h12a2 2 0 0 0 1.9-1.4L21 12H7l-4 6" />
    </>
  ),
  package: <path d="m12 3 9 5-9 5-9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5" />,
  play: <path d="m8 5 11 7-11 7Z" />,
  plus: <path d="M12 5v14M5 12h14" />,
  save: (
    <>
      <path d="M5 3h12l4 4v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" />
      <path d="M7 3v6h9V3M7 21v-7h10v7" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-4-4" />
    </>
  ),
  send: <path d="m22 2-7 20-4-9-9-4Zm0 0L11 13" />,
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14h-.2v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" />
    </>
  ),
  shield: (
    <>
      <path d="m12 3-8 3v5c0 5 3.4 8.5 8 10 4.6-1.5 8-5 8-10V6Z" />
      <path d="m9 12 2 2 4-5" />
    </>
  ),
  stop: <rect x="6" y="6" width="12" height="12" rx="2" />,
  table: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M3 9h18M3 14h18M9 9v11m6-11v11" />
    </>
  ),
  terminal: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="m7 9 3 3-3 3m6 0h4" />
    </>
  ),
  trash: <path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14M10 11v6m4-6v6" />,
  trigger: <path d="m13 2-9 12h7l-1 8 9-12h-7Z" />,
  variable: (
    <path d="M7 4H5a2 2 0 0 0-2 2v4a2 2 0 0 1-2 2 2 2 0 0 1 2 2v4a2 2 0 0 0 2 2h2m10-16h2a2 2 0 0 1 2 2v4a2 2 0 0 0 2 2 2 2 0 0 0-2 2v4a2 2 0 0 1-2 2h-2M9 9l6 6m0-6-6 6" />
  ),
  warn: (
    <>
      <path d="M12 3 2 21h20Z" />
      <path d="M12 9v5m0 4h.01" />
    </>
  ),
};

export function Icon({
  name,
  className = "",
}: {
  name: IconName;
  className?: string;
}) {
  return (
    <svg
      aria-hidden="true"
      className={`app-icon ${className}`}
      focusable="false"
      viewBox="0 0 24 24"
    >
      {paths[name]}
    </svg>
  );
}

export function nodeVisual(type: string, category = "") {
  const value = `${category} ${type}`.toLowerCase();
  if (value.includes("excel"))
    return { icon: "excel" as IconName, tone: "excel" };
  if (/agent|llm|prompt|memory/.test(value))
    return { icon: "agent" as IconName, tone: "agent" };
  if (/python|script|shell|code|polars|formula/.test(value))
    return { icon: "code" as IconName, tone: "code" };
  if (/file|path|folder|csv|parquet|json/.test(value))
    return { icon: "folder" as IconName, tone: "file" };
  if (/trigger/.test(value))
    return { icon: "trigger" as IconName, tone: "flow" };
  if (/variable/.test(value))
    return { icon: "variable" as IconName, tone: "flow" };
  if (/filter/.test(value))
    return { icon: "filter" as IconName, tone: "table" };
  if (/group|join|concat|pivot/.test(value))
    return { icon: "group" as IconName, tone: "table" };
  if (/table|row|column|sort|duplicate|missing|cast/.test(value))
    return { icon: "table" as IconName, tone: "table" };
  return { icon: "flow" as IconName, tone: "flow" };
}
