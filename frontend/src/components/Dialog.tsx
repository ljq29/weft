import {
  useEffect,
  useId,
  useRef,
  type FormEvent,
  type ReactNode,
  type RefObject,
} from "react";
import { Icon } from "./Icon";

const focusableSelector = [
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "a[href]",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

interface DialogProps {
  title: string;
  children: ReactNode;
  onClose: () => void;
  footer?: ReactNode;
  error?: string;
  initialFocusRef?: RefObject<HTMLElement | null>;
  className?: string;
}

export function Dialog({
  title,
  children,
  onClose,
  footer,
  error,
  initialFocusRef,
  className = "",
}: DialogProps) {
  const titleId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const previous = document.activeElement;
    const root = rootRef.current;
    const target =
      initialFocusRef?.current ??
      root?.querySelector<HTMLElement>("[autofocus]") ??
      root?.querySelector<HTMLElement>(focusableSelector);
    target?.focus();
    return () => {
      if (previous instanceof HTMLElement && previous.isConnected) {
        previous.focus();
      }
    };
  }, [initialFocusRef]);

  return (
    <div
      ref={rootRef}
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      data-weft-dialog
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          event.stopPropagation();
          closeRef.current();
          return;
        }
        if (event.key !== "Tab") return;
        const items = Array.from(
          event.currentTarget.querySelectorAll<HTMLElement>(focusableSelector),
        ).filter((item) => item.getClientRects().length > 0);
        if (!items.length) {
          event.preventDefault();
          return;
        }
        const first = items[0];
        const last = items.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }}
    >
      <section className={`modal form-modal ${className}`.trim()}>
        <header className="modal-header">
          <div>
            <div>
              <h2 id={titleId}>{title}</h2>
            </div>
          </div>
          <button className="icon-button" aria-label="关闭" onClick={onClose}>
            <Icon name="close" />
          </button>
        </header>
        <div className="form-modal-body">{children}</div>
        {error && (
          <div className="error-banner" role="alert">
            <Icon name="warn" />
            <span>{error}</span>
          </div>
        )}
        {footer && <footer className="modal-footer">{footer}</footer>}
      </section>
    </div>
  );
}

export function ConfirmDialog({
  title,
  message,
  confirmLabel = "继续",
  cancelLabel = "取消",
  error,
  onConfirm,
  onCancel,
}: {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  error?: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const confirmRef = useRef<HTMLButtonElement>(null);
  return (
    <Dialog
      title={title}
      error={error}
      initialFocusRef={confirmRef}
      onClose={onCancel}
      footer={
        <div>
          <button className="button secondary" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            className="button primary"
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      }
    >
      <p className="dialog-message">{message}</p>
    </Dialog>
  );
}

export interface DialogField {
  name: string;
  label: string;
  defaultValue?: string;
}

export function FormDialog({
  title,
  fields,
  submitLabel,
  error,
  onSubmit,
  onCancel,
}: {
  title: string;
  fields: DialogField[];
  submitLabel: string;
  error?: string;
  onSubmit: (values: Record<string, string>) => void;
  onCancel: () => void;
}) {
  const firstInputRef = useRef<HTMLInputElement>(null);
  const formId = useId();
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    onSubmit(
      Object.fromEntries(
        fields.map((field) => {
          const value = data.get(field.name);
          return [field.name, typeof value === "string" ? value : ""];
        }),
      ),
    );
  };
  return (
    <Dialog
      title={title}
      error={error}
      initialFocusRef={firstInputRef}
      onClose={onCancel}
      footer={
        <div>
          <button className="button secondary" onClick={onCancel}>
            取消
          </button>
          <button className="button primary" type="submit" form={formId}>
            {submitLabel}
          </button>
        </div>
      }
    >
      <form id={formId} onSubmit={submit}>
        {fields.map((field, index) => (
          <label className="form-field" key={field.name}>
            <span>{field.label}</span>
            <input
              ref={index === 0 ? firstInputRef : undefined}
              aria-label={field.label}
              name={field.name}
              defaultValue={field.defaultValue ?? ""}
              required
            />
          </label>
        ))}
      </form>
    </Dialog>
  );
}
