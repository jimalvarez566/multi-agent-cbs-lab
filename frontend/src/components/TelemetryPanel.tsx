import { Activity } from "lucide-react";
import type { Solution } from "../types";
export function TelemetryPanel({ solution }: { solution: Solution | null }) {
  const c = solution?.metrics,
    b = solution?.baseline.metrics;
  const rows = [
    ["Makespan", c?.makespan, b?.makespan, "steps"],
    ["Sum of costs", c?.sum_of_costs, b?.sum_of_costs, "steps"],
    ["Conflicts resolved", c?.conflicts_resolved, b?.conflicts_resolved, ""],
    ["Remaining collisions", c?.collisions, b?.collisions, ""],
    ["Execution time", c?.execution_time_ms, b?.execution_time_ms, "ms"],
  ] as const;
  return (
    <section className="panel telemetry">
      <div className="section-label">
        <Activity size={15} /> LIVE TELEMETRY
      </div>
      <h2>Coordination pays off.</h2>
      <p className="muted">Optimal planning vs. independent routes.</p>
      <table>
        <thead>
          <tr>
            <th>METRIC</th>
            <th className="teal">CBS</th>
            <th>BASELINE</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, a, b, unit]) => (
            <tr key={label}>
              <td>{label}</td>
              <td className="teal">
                {a === undefined ? "—" : unit === "ms" ? a.toFixed(2) : a}
                <small>{a === undefined ? "" : unit}</small>
              </td>
              <td>
                {b === undefined ? "—" : unit === "ms" ? b.toFixed(2) : b}
                <small>{b === undefined ? "" : unit}</small>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="telemetry-note">
        <span className="dot" />
        {solution
          ? `${solution.expanded_nodes} tree nodes explored · ${solution.metrics.collisions} CBS collisions`
          : "Run a scenario to compare planners"}
      </div>
      {solution?.obstacle && (
        <p className="orange text-xs mt-3">
          Bottleneck at ({solution.obstacle.join(", ")}) ·{" "}
          {solution.traffic_score} future visits. Baseline ignores the temporary
          obstacle.
        </p>
      )}
    </section>
  );
}
