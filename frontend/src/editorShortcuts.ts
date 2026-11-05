import { useEffect, useRef } from "react";

export interface EditorShortcutActions {
  save: () => void;
  undo: () => void;
  redo: () => void;
  copy: () => void;
  paste: () => void;
  deleteSelected: () => void;
  fitView: () => void;
  fitSelected: () => void;
  escape: () => boolean;
}

export function isTextEditingTarget(target: EventTarget | null): boolean {
  if (!target || typeof target !== "object") return false;
  const element = target as Partial<HTMLElement>;
  if (
    ["input", "textarea", "select"].includes(
      element.tagName?.toLowerCase() ?? "",
    )
  )
    return true;
  if (element.isContentEditable) return true;
  if (typeof element.closest !== "function") return false;
  return Boolean(
    element.closest(
      'input, textarea, select, [contenteditable=""], [contenteditable="true"], [contenteditable="plaintext-only"]',
    ),
  );
}

export function handleEditorShortcut(
  event: KeyboardEvent,
  actions: EditorShortcutActions,
): void {
  if (event.defaultPrevented) return;
  const key = event.key.toLowerCase();
  const target = event.target as Partial<HTMLElement> | null;
  const inDialog = Boolean(target?.closest?.("[data-weft-dialog]"));
  if (key === "escape" && inDialog) return;
  if (key === "escape") {
    if (actions.escape()) {
      event.preventDefault();
      event.stopPropagation();
    }
    return;
  }
  if (event.ctrlKey && key === "s") {
    event.preventDefault();
    actions.save();
    return;
  }
  if (isTextEditingTarget(event.target) || inDialog) return;

  if (event.shiftKey && key === "1") {
    event.preventDefault();
    actions.fitView();
    return;
  }
  if (event.shiftKey && key === "2") {
    event.preventDefault();
    actions.fitSelected();
    return;
  }
  if (key === "delete") {
    event.preventDefault();
    actions.deleteSelected();
    return;
  }
  if (!event.ctrlKey) return;

  if (key === "z") {
    event.preventDefault();
    if (event.shiftKey) actions.redo();
    else actions.undo();
  } else if (key === "y") {
    event.preventDefault();
    actions.redo();
  } else if (key === "c") {
    event.preventDefault();
    actions.copy();
  } else if (key === "v") {
    event.preventDefault();
    actions.paste();
  }
}

export function useEditorShortcuts(actions: EditorShortcutActions): void {
  const actionsRef = useRef(actions);
  actionsRef.current = actions;

  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      handleEditorShortcut(event, actionsRef.current);
    };
    window.addEventListener("keydown", listener, true);
    return () => {
      window.removeEventListener("keydown", listener, true);
    };
  }, []);
}
