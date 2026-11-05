import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ConnectionIndicatorView } from "./ConnectionIndicator";
import {
  setReconnectHandler,
  useConnectionStore,
} from "../stores/connectionStore";

describe("ConnectionIndicator", () => {
  afterEach(() => {
    setReconnectHandler(null);
    useConnectionStore.setState({
      status: "idle",
      workflowId: "",
      attempt: 0,
      retryAt: null,
      error: "",
    });
  });

  it("US-EXE-05/AC-3: exposes connection state and an immediate reconnect action", () => {
    const reconnect = vi.fn();
    setReconnectHandler(reconnect);
    useConnectionStore.setState({
      status: "backoff",
      workflowId: "wf_1",
      attempt: 2,
      retryAt: 1000,
      error: "connection lost",
    });
    const html = renderToStaticMarkup(
      <ConnectionIndicatorView
        status="backoff"
        attempt={2}
        error="connection lost"
        reconnect={reconnect}
      />,
    );
    expect(html).toContain("等待重连");
    expect(html).toContain("第 2 次");
    expect(html).toContain("立即重连");
    expect(html).toContain('title="connection lost"');
    useConnectionStore.getState().reconnect();
    expect(reconnect).toHaveBeenCalledOnce();
  });
});
