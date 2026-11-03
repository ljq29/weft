export type PortType =
  "table" | "excel" | "variable" | "message" | "tool" | "flow";

export interface PortDecl {
  name: string;
  kind: PortType;
  description: string;
}

export interface NodeTypeDecl {
  type: string;
  name: string;
  description: string;
  category: string;
  cache_policy: string;
  inputs: PortDecl[];
  outputs: PortDecl[];
  params_schema: Record<string, unknown>;
}

export interface WorkflowNodeData extends Record<string, unknown> {
  nodeId: string;
  type: string;
  name: string;
  params: Record<string, unknown>;
  inputs: PortDecl[];
  outputs: PortDecl[];
  comment: string;
  status: string;
  error?: { message: string; traceback?: string };
  iteration?: { index: number; total: number };
  workflowId?: string;
}

export interface CanvasNote {
  id: string;
  position: { x: number; y: number };
  size: { width: number; height: number };
  color: string;
  markdown: string;
}

export interface WorkflowDocument {
  schema_version: number;
  revision: number;
  id: string;
  name: string;
  description: string;
  created_at: string;
  modified_at: string;
  settings: Record<string, unknown>;
  variables: { name: string; type: string; value: unknown }[];
  notes: CanvasNote[];
  viewport: { x: number; y: number; zoom: number };
  nodes: {
    id: string;
    type: string;
    node_version: number;
    name: string;
    position: { x: number; y: number };
    params: Record<string, unknown>;
    comment?: string;
  }[];
  edges: {
    id: string;
    source: string;
    sourcePort: string;
    target: string;
    targetPort: string;
    order: number;
  }[];
}
