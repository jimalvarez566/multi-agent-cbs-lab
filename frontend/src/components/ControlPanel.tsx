import { Play, Zap, SlidersHorizontal } from "lucide-react";
import type { Preset } from "../scenarios";
interface Props {
  size: number;
  fleet: number;
  preset: Preset;
  busy: boolean;
  canDisrupt: boolean;
  configure: (s: number, f: number, p: Preset) => void;
  run: (d?: boolean) => void;
}
export function ControlPanel(p: Props) {
  return (
    <section className="panel controls">
      <div className="section-label">
        <SlidersHorizontal size={15} /> SCENARIO CONFIGURATION
      </div>
      <h2>Build your environment</h2>
      <p className="muted">Set the stage. Let the agents find their way.</p>
      <label className="slider-label">
        Grid dimensions{" "}
        <strong>
          {p.size} × {p.size}
        </strong>
      </label>
      <input
        aria-label="Grid dimensions"
        type="range"
        min="8"
        max="20"
        value={p.size}
        disabled={p.busy}
        onChange={(e) => p.configure(+e.target.value, p.fleet, p.preset)}
      />
      <div className="range-labels">
        <span>8 × 8</span>
        <span>20 × 20</span>
      </div>
      <label className="slider-label">
        Fleet size <strong>{p.fleet} agents</strong>
      </label>
      <input
        aria-label="Fleet size"
        type="range"
        min="2"
        max="6"
        value={p.fleet}
        disabled={p.busy}
        onChange={(e) => p.configure(p.size, +e.target.value, p.preset)}
      />
      <div className="range-labels">
        <span>02</span>
        <span>06</span>
      </div>
      <div className="section-label mt-7">ENVIRONMENT PRESETS</div>
      {(
        ["Narrow Hallway", "Crossroad Bottleneck", "Random Grid"] as Preset[]
      ).map((name, i) => (
        <button
          disabled={p.busy}
          key={name}
          className={`preset ${p.preset === name ? "selected" : ""}`}
          onClick={() => p.configure(p.size, p.fleet, name)}
        >
          <span className="preset-icon">{["Ⅱ", "✛", "▦"][i]}</span>
          <span>
            {name}
            <small>
              {
                [
                  "Opposing traffic through a narrow passage",
                  "Shared intersections, competing routes",
                  "Scattered obstacles, open possibilities",
                ][i]
              }
            </small>
          </span>
          <span className="radio" />
        </button>
      ))}
      <button className="primary" disabled={p.busy} onClick={() => p.run()}>
        <Play size={16} />
        {p.busy ? "Planning routes…" : "Solve with CBS"}
      </button>
      <div className="adversary">
        <div className="section-label orange">
          <Zap size={14} /> ADVERSARIAL REPLANNING
        </div>
        <p>
          Block the busiest future cell for 4 steps and watch the fleet adapt.
        </p>
        <button
          className="disrupt"
          disabled={p.busy || !p.canDisrupt}
          onClick={() => p.run(true)}
        >
          <Zap size={15} /> Run Dynamic Bottleneck
        </button>
      </div>
    </section>
  );
}
