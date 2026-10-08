import { useState } from "react";
import {
  Layers3,
  Play,
  Pause,
  SkipBack,
  SkipForward,
  RotateCcw,
  ArrowUpRight,
  Route,
} from "lucide-react";
import { useSimulation } from "./hooks/useSimulation";
import { ControlPanel } from "./components/ControlPanel";
import { SimulationCanvas } from "./components/SimulationCanvas";
import { TelemetryPanel } from "./components/TelemetryPanel";
import { ConflictTreeViewer } from "./components/ConflictTreeViewer";
import { COLORS } from "./types";
export default function App() {
  const s = useSimulation();
  const [ribbons, setRibbons] = useState(true);
  const seek = (t: number) => {
    s.setPlaying(false);
    s.setTime(Math.max(0, Math.min(s.makespan, t)));
  };
  return (
    <div className="app-shell">
      <header>
        <a className="brand" href="/">
          <span className="brand-mark">
            <Layers3 size={22} />
          </span>
          flux
          <span className="brand-divider" />{" "}
          <span className="brand-sub">MULTI-AGENT PATHFINDING LAB</span>
        </a>
        <div className="header-right">
          <span className="status">
            <span className="dot" />
            {s.busy ? "PLANNER RUNNING" : "SIMULATION WORKSPACE"}
          </span>
          <a href="/docs" target="_blank" rel="noreferrer">
            API docs <ArrowUpRight size={13} />
          </a>
        </div>
      </header>
      <main>
        <div className="page-intro">
          <div>
            <div className="eyebrow">COORDINATE. DISRUPT. ADAPT.</div>
            <h1>Every agent. One clear path.</h1>
            <p>
              Explore conflict-based search and real-time bottleneck replanning.
            </p>
          </div>
          <span className="algorithm-tag">
            <Route size={15} /> CBS + SPACE-TIME A*
          </span>
        </div>
        <div className="workspace">
          <ControlPanel
            {...s}
            canDisrupt={
              !!s.solution &&
              !(
                s.solution.obstacle &&
                s.time <= (s.solution.obstacle_duration ?? 0)
              )
            }
          />
          <section className="panel stage">
            <div className="stage-heading">
              <div>
                <div className="section-label">SIMULATION ENVIRONMENT</div>
                <h2>{s.preset}</h2>
              </div>
              <span className={`live-pill ${s.playing ? "active" : ""}`}>
                <span className="dot" />
                {s.busy
                  ? "PLANNING"
                  : s.playing
                    ? "LIVE"
                    : s.solution
                      ? "READY"
                      : "IDLE"}
              </span>
            </div>
            <div className="grid-info">
              <span>
                {s.size} × {s.size} grid
              </span>
              <span>{s.fleet} agents</span>
              <label>
                <input
                  type="checkbox"
                  checked={ribbons}
                  onChange={(e) => setRibbons(e.target.checked)}
                />{" "}
                Path ribbons
              </label>
            </div>
            <div className="canvas-wrap">
              <SimulationCanvas
                scenario={s.scenario}
                solution={s.solution}
                time={s.time}
                ribbons={ribbons}
              />
            </div>
            <div className="agent-legend">
              {s.scenario.agents.map((a, i) => (
                <span key={a.id}>
                  <i style={{ background: COLORS[i] }} />
                  {a.id}
                </span>
              ))}
              <span className="legend-key">□ Start &nbsp; ◎ Goal</span>
            </div>
            <div className="playback">
              <div className="playback-top">
                <span>PLAYBACK</span>
                <span className="mono">
                  STEP <strong>{s.time.toFixed(1)}</strong> / {s.makespan}
                </span>
              </div>
              <input
                aria-label="Playback step"
                type="range"
                min="0"
                max={s.makespan || 1}
                step="0.01"
                value={s.time}
                disabled={!s.solution || s.busy}
                onChange={(e) => seek(+e.target.value)}
              />
              <div className="transport">
                <button
                  aria-label="Rewind"
                  disabled={!s.solution || s.busy}
                  onClick={() => seek(0)}
                >
                  <RotateCcw size={16} />
                </button>
                <button
                  aria-label="Previous step"
                  disabled={!s.solution || s.busy}
                  onClick={() => seek(Math.ceil(s.time) - 1)}
                >
                  <SkipBack size={17} />
                </button>
                <button
                  className="play-button"
                  aria-label={s.playing ? "Pause" : "Play"}
                  disabled={!s.solution || s.busy}
                  onClick={() => {
                    if (s.time >= s.makespan) s.setTime(0);
                    s.setPlaying(!s.playing);
                  }}
                >
                  {s.playing ? <Pause size={18} /> : <Play size={18} />}
                </button>
                <button
                  aria-label="Next step"
                  disabled={!s.solution || s.busy}
                  onClick={() => seek(Math.floor(s.time) + 1)}
                >
                  <SkipForward size={17} />
                </button>
                <select
                  aria-label="Playback speed"
                  value={s.speed}
                  onChange={(e) => s.setSpeed(+e.target.value)}
                >
                  <option value="0.5">0.5× speed</option>
                  <option value="1">1× speed</option>
                  <option value="2">2× speed</option>
                  <option value="4">4× speed</option>
                </select>
              </div>
            </div>
          </section>
          <aside>
            <TelemetryPanel solution={s.solution} />
            <ConflictTreeViewer solution={s.solution} />
          </aside>
        </div>
        {s.error && (
          <div className="error" role="alert">
            {s.error}
          </div>
        )}
        <footer>
          <span>
            <span className="dot" /> Collision-free coordination · Dynamic
            environments
          </span>
          <span>MAPF RESEARCH WORKSPACE / v1.0</span>
        </footer>
      </main>
    </div>
  );
}
