import { describe, expect, it, vi } from "vitest";
import {
  handleEditorShortcut,
  isTextEditingTarget,
  type EditorShortcutActions,
} from "./editorShortcuts";

function actions(escapeResult = false) {
  return {
    save: vi.fn(),
    undo: vi.fn(),
    redo: vi.fn(),
    copy: vi.fn(),
    paste: vi.fn(),
    deleteSelected: vi.fn(),
    fitView: vi.fn(),
    fitSelected: vi.fn(),
    escape: vi.fn(() => escapeResult),
  } satisfies EditorShortcutActions;
}

function keyboardEvent(
  key: string,
  init: {
    target?: EventTarget | null;
    ctrlKey?: boolean;
    shiftKey?: boolean;
    defaultPrevented?: boolean;
  } = {},
) {
  const preventDefault = vi.fn();
  const event = {
    key,
    target: null,
    ctrlKey: false,
    shiftKey: false,
    defaultPrevented: false,
    preventDefault,
    stopPropagation: vi.fn(),
    ...init,
  } as unknown as KeyboardEvent;
  return { event, preventDefault };
}

describe("editor keyboard shortcuts", () => {
  it("US-DES-08/AC-1,2,3: keeps editing shortcuts on the canvas", () => {
    const spies = actions();
    const cases = [
      ["s", "save"],
      ["z", "undo"],
      ["y", "redo"],
      ["c", "copy"],
      ["v", "paste"],
    ] as const;
    for (const [key, action] of cases) {
      const { event, preventDefault } = keyboardEvent(key, { ctrlKey: true });
      handleEditorShortcut(event, spies);
      expect(spies[action]).toHaveBeenCalledOnce();
      expect(preventDefault).toHaveBeenCalledOnce();
    }
    const deletion = keyboardEvent("Delete");
    handleEditorShortcut(deletion.event, spies);
    expect(spies.deleteSelected).toHaveBeenCalledOnce();
    expect(deletion.preventDefault).toHaveBeenCalledOnce();
  });

  it("US-DES-08/AC-1: Ctrl+Shift+Z redoes without undoing", () => {
    const spies = actions();
    const { event, preventDefault } = keyboardEvent("z", {
      ctrlKey: true,
      shiftKey: true,
    });
    handleEditorShortcut(event, spies);
    expect(spies.redo).toHaveBeenCalledOnce();
    expect(spies.undo).not.toHaveBeenCalled();
    expect(preventDefault).toHaveBeenCalledOnce();
  });

  it("US-DES-11/AC-1: keeps fit-view shortcuts on the canvas", () => {
    const spies = actions();
    handleEditorShortcut(keyboardEvent("1", { shiftKey: true }).event, spies);
    handleEditorShortcut(keyboardEvent("2", { shiftKey: true }).event, spies);
    expect(spies.fitView).toHaveBeenCalledOnce();
    expect(spies.fitSelected).toHaveBeenCalledOnce();
  });

  it("US-DES-08/AC-1,2,3: text controls keep native editing behavior", () => {
    const targets = [
      { tagName: "INPUT" },
      { tagName: "TEXTAREA" },
      { isContentEditable: true },
    ] as unknown as EventTarget[];
    for (const target of targets) {
      const spies = actions();
      for (const key of ["Delete", "c", "v", "z", "y", "1"]) {
        const { event, preventDefault } = keyboardEvent(key, {
          target,
          ctrlKey: key !== "Delete" && key !== "1",
          shiftKey: key === "1",
        });
        handleEditorShortcut(event, spies);
        expect(preventDefault).not.toHaveBeenCalled();
      }
      for (const action of [
        spies.deleteSelected,
        spies.copy,
        spies.paste,
        spies.undo,
        spies.redo,
        spies.fitView,
      ]) {
        expect(action).not.toHaveBeenCalled();
      }
    }
  });

  it("US-DES-07/AC-2: Ctrl+S still saves while a text input is focused", () => {
    const spies = actions();
    const { event, preventDefault } = keyboardEvent("s", {
      target: { tagName: "INPUT" } as unknown as EventTarget,
      ctrlKey: true,
    });
    handleEditorShortcut(event, spies);
    expect(spies.save).toHaveBeenCalledOnce();
    expect(spies.copy).not.toHaveBeenCalled();
    expect(preventDefault).toHaveBeenCalledOnce();
  });

  it("recognizes descendants of contenteditable regions", () => {
    const editable = { getAttribute: () => "true" };
    const target = {
      tagName: "SPAN",
      isContentEditable: false,
      closest: (selector: string) =>
        selector.includes("[contenteditable") ? editable : null,
    } as unknown as EventTarget;
    expect(isTextEditingTarget(target)).toBe(true);
    expect(isTextEditingTarget(null)).toBe(false);
  });

  it("US-DES-08/AC-1: leaves dialog Escape and canvas editing keys to the dialog", () => {
    const target = {
      tagName: "BUTTON",
      closest: (selector: string) =>
        selector === "[data-weft-dialog]" ? {} : null,
    } as unknown as EventTarget;
    const spies = actions(true);
    const escape = keyboardEvent("Escape", { target });
    handleEditorShortcut(escape.event, spies);
    expect(spies.escape).not.toHaveBeenCalled();
    expect(escape.preventDefault).not.toHaveBeenCalled();

    handleEditorShortcut(keyboardEvent("Delete", { target }).event, spies);
    handleEditorShortcut(
      keyboardEvent("1", { target, shiftKey: true }).event,
      spies,
    );
    expect(spies.deleteSelected).not.toHaveBeenCalled();
    expect(spies.fitView).not.toHaveBeenCalled();
  });

  it("delegates Escape and only prevents a handled dismissal", () => {
    const spies = actions(true);
    const handled = keyboardEvent("Escape");
    handleEditorShortcut(handled.event, spies);
    expect(spies.escape).toHaveBeenCalledOnce();
    expect(handled.preventDefault).toHaveBeenCalledOnce();

    const unhandled = keyboardEvent("Escape");
    handleEditorShortcut(unhandled.event, actions(false));
    expect(unhandled.preventDefault).not.toHaveBeenCalled();
  });

  it("US-TBL-08/AC-5: leaves Ctrl+Enter to the code editor", () => {
    const spies = actions();
    const { event, preventDefault } = keyboardEvent("Enter", {
      target: { tagName: "TEXTAREA" } as unknown as EventTarget,
      ctrlKey: true,
    });
    handleEditorShortcut(event, spies);
    expect(preventDefault).not.toHaveBeenCalled();
    for (const action of Object.values(spies)) {
      expect(action).not.toHaveBeenCalled();
    }
  });

  it("respects events already handled by a focused control", () => {
    const spies = actions();
    const { event } = keyboardEvent("Enter", {
      ctrlKey: true,
      defaultPrevented: true,
    });
    handleEditorShortcut(event, spies);
    expect(spies.escape).not.toHaveBeenCalled();
    expect(spies.save).not.toHaveBeenCalled();
  });
});
