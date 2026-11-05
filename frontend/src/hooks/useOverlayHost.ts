import { useCallback, useState } from "react";
import type { DialogField } from "../components/Dialog";

interface OverlayBase {
  title: string;
  onCancel: () => void;
}

export type OverlayRequest =
  | (OverlayBase & {
      kind: "form";
      fields: DialogField[];
      submitLabel: string;
      onSubmit: (values: Record<string, string>) => void;
    })
  | (OverlayBase & {
      kind: "confirm";
      message: string;
      confirmLabel?: string;
      cancelLabel?: string;
      onConfirm: () => void;
    })
  | (OverlayBase & {
      kind: "message";
      message: string;
    });

export interface OverlayOptions {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
}

export function useOverlayHost() {
  const [request, setRequest] = useState<OverlayRequest | null>(null);
  const close = useCallback(() => {
    setRequest(null);
  }, []);

  const form = useCallback(
    (
      title: string,
      fields: DialogField[],
      submitLabel: string,
    ): Promise<Record<string, string> | null> =>
      new Promise((resolve) => {
        setRequest({
          kind: "form",
          title,
          fields,
          submitLabel,
          onSubmit: (values) => {
            close();
            resolve(values);
          },
          onCancel: () => {
            close();
            resolve(null);
          },
        });
      }),
    [close],
  );

  const confirm = useCallback(
    ({
      title,
      message,
      confirmLabel,
      cancelLabel,
    }: OverlayOptions): Promise<boolean> =>
      new Promise((resolve) => {
        setRequest({
          kind: "confirm",
          title,
          message,
          confirmLabel,
          cancelLabel,
          onConfirm: () => {
            close();
            resolve(true);
          },
          onCancel: () => {
            close();
            resolve(false);
          },
        });
      }),
    [close],
  );

  const message = useCallback(
    (title: string, text: string): Promise<void> =>
      new Promise((resolve) => {
        setRequest({
          kind: "message",
          title,
          message: text,
          onCancel: () => {
            close();
            resolve();
          },
        });
      }),
    [close],
  );

  return { request, form, confirm, message };
}
