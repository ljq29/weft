import { ConfirmDialog, Dialog, FormDialog } from "./Dialog";
import type { OverlayRequest } from "../hooks/useOverlayHost";

export function OverlayHost({ request }: { request: OverlayRequest | null }) {
  if (!request) return null;
  if (request.kind === "form") {
    return (
      <FormDialog
        title={request.title}
        fields={request.fields}
        submitLabel={request.submitLabel}
        onSubmit={request.onSubmit}
        onCancel={request.onCancel}
      />
    );
  }
  if (request.kind === "confirm") {
    return (
      <ConfirmDialog
        title={request.title}
        message={request.message}
        confirmLabel={request.confirmLabel}
        cancelLabel={request.cancelLabel}
        onConfirm={request.onConfirm}
        onCancel={request.onCancel}
      />
    );
  }
  return (
    <Dialog
      title={request.title}
      onClose={request.onCancel}
      footer={
        <div>
          <button className="button primary" onClick={request.onCancel}>
            确定
          </button>
        </div>
      }
    >
      <p className="dialog-message">{request.message}</p>
    </Dialog>
  );
}
