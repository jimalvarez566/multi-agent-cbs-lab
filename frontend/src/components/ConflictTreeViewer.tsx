import { useState } from "react";
import { GitBranch } from "lucide-react";
import type { Solution } from "../types";
export function ConflictTreeViewer({
  solution,
}: {
  solution: Solution | null;
}) {
  const [all, setAll] = useState(false);
  const nodes = solution?.tree ?? [];
  const visible = all ? nodes : nodes.slice(0, 60);
  return (
    <section className="panel tree">
      <div className="section-label">
        <GitBranch size={15} /> CONSTRAINT TREE{" "}
        <span className="badge">{solution?.node_count ?? 0} nodes</span>
      </div>
      <h2>Inside the search</h2>
      <p className="muted">
        Disjoint branches reserve or forbid a conflict event.
      </p>
      <div className="tree-list">
        {!nodes.length && (
          <div className="empty-tree">
            <GitBranch size={30} />
            <p>The search tree will appear here.</p>
          </div>
        )}
        {visible.map((n) => (
          <details
            key={n.id}
            className={`tree-node ${n.status === "solution" ? "solved" : ""}`}
          >
            <summary>
              <span>
                #{n.id} {n.parent_id !== null ? `← #${n.parent_id}` : "Root"}
              </span>
              <span>
                SIC {n.cost} <small>{n.status}</small>
              </span>
            </summary>
            <p>
              {n.conflict
                ? `${n.conflict.kind} conflict · ${n.conflict.agents.join(" / ")} · step ${n.conflict.time}`
                : "No recorded conflict"}
              {n.constraint && (
                <>
                  <br />
                  {n.constraint.positive ? "Reserve" : "Forbid"}:{" "}
                  {n.constraint.agent} at step {n.constraint.time}
                  <br />
                  Replanned: {n.replanned_agents?.join(", ") || "none"}
                </>
              )}
            </p>
          </details>
        ))}
      </div>
      {nodes.length > 60 && (
        <button className="text-button" onClick={() => setAll(!all)}>
          {all ? "Show first 60 nodes" : `Show all ${nodes.length} nodes`}
        </button>
      )}
    </section>
  );
}
