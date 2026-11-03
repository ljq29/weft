import { useState } from "react";
import { api } from "../api/client";

interface Entry {
  name: string;
  path: string;
  is_dir: boolean;
}

export function toPortablePath(path: string, root: string): string {
  const normalized = path.replaceAll("\\", "/");
  const prefix = root.replaceAll("\\", "/").replace(/\/$/, "") + "/";
  return normalized.startsWith(prefix) ? normalized.slice(prefix.length) : path;
}

export function PathField({
  label,
  value,
  root,
  onChange,
}: {
  label: string;
  value: string;
  root: string;
  onChange: (value: string) => void;
}) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const browse = async () => {
    const response = await api<{ entries: Entry[] }>("/fs/browse", {
      method: "POST",
      body: JSON.stringify({ path: root, dirs_only: false }),
    });
    setEntries(response.entries);
  };
  const select = (path: string) => {
    onChange(toPortablePath(path, root));
  };
  const isAbsolute = /^[a-zA-Z]:[\\/]/.test(value) || value.startsWith("/");
  return (
    <>
      <input
        aria-label={label}
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
      <button type="button" onClick={() => void browse()}>
        选择路径
      </button>
      {entries.length > 0 && (
        <select
          aria-label={`${label}候选项`}
          onChange={(event) => {
            select(event.target.value);
          }}
        >
          <option value="">选择文件或目录</option>
          {entries.map((entry) => (
            <option key={entry.path} value={entry.path}>
              {entry.name}
            </option>
          ))}
        </select>
      )}
      {isAbsolute && <small>绝对路径不可移植</small>}
    </>
  );
}
