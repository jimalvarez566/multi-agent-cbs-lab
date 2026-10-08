export type Point = [number, number];
export interface Agent {
  id: string;
  start: Point;
  goal: Point;
}
export interface Scenario {
  width: number;
  height: number;
  obstacles: Point[];
  agents: Agent[];
}
export interface Metrics {
  makespan: number;
  sum_of_costs: number;
  collisions: number;
  conflicts_resolved: number;
  execution_time_ms: number;
}
export interface Conflict {
  kind: "vertex" | "edge";
  time: number;
  agents: string[];
  position: Point;
}
export interface TreeNode {
  id: number;
  parent_id: number | null;
  cost: number;
  status: string;
  conflict: Conflict | null;
  constraint?: { agent: string; time: number; positive: boolean };
  replanned_agents?: string[];
}
export interface Solution {
  paths: Record<string, Point[]>;
  metrics: Metrics;
  baseline: { paths: Record<string, Point[]>; metrics: Metrics };
  tree: TreeNode[];
  node_count: number;
  expanded_nodes: number;
  solve_duration_ms: number;
  obstacle?: Point;
  obstacle_duration?: number;
  traffic_score?: number;
  agents?: Agent[];
}
export const COLORS = [
  "#2dd4bf",
  "#fb923c",
  "#e879f9",
  "#60a5fa",
  "#facc15",
  "#a3e635",
];
