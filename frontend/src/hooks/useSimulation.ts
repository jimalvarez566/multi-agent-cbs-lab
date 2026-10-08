import { useEffect, useRef, useState } from "react";
import { createScenario, type Preset } from "../scenarios";
import type { Scenario, Solution } from "../types";

export function useSimulation() {
  const [size, setSize] = useState(12),
    [fleet, setFleet] = useState(3);
  const [preset, setPreset] = useState<Preset>("Narrow Hallway");
  const [scenario, setScenario] = useState<Scenario>(() =>
    createScenario(12, 3, "Narrow Hallway"),
  );
  const [solution, setSolution] = useState<Solution | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [time, setTime] = useState(0),
    [playing, setPlaying] = useState(false),
    [speed, setSpeed] = useState(1);
  const controller = useRef<AbortController | null>(null);
  const makespan = solution?.metrics.makespan ?? 0;
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (!playing) return;
    let frame = 0,
      last = performance.now();
    const tick = (now: number) => {
      // rAF timestamps can precede a clock reading taken mid-frame.
      const elapsed = Math.max(0, Math.min((now - last) / 1000, 0.1));
      last = now;
      setTime((t) => Math.min(makespan, t + elapsed * speed * 1.5));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, speed, makespan]);
  useEffect(() => {
    if (time >= makespan) setPlaying(false);
  }, [time, makespan]);
  function configure(n: number, count: number, p: Preset) {
    controller.current?.abort();
    controller.current = null;
    setBusy(false);
    setSize(n);
    setFleet(count);
    setPreset(p);
    setScenario(createScenario(n, count, p));
    setSolution(null);
    setTime(0);
    setPlaying(false);
    setError("");
  }
  async function run(dynamic = false) {
    if (
      busy ||
      (dynamic &&
        (!solution ||
          (solution.obstacle && time <= (solution.obstacle_duration ?? 0))))
    )
      return;
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true);
    setError("");
    setPlaying(false);
    try {
      const response = await fetch(
        dynamic ? "/api/adversary/disrupt" : "/api/solve",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: abort.signal,
          body: JSON.stringify(
            dynamic
              ? {
                  ...scenario,
                  paths: solution!.paths,
                  current_time: Math.floor(time),
                  obstacle_duration: 4,
                }
              : scenario,
          ),
        },
      );
      const data = await response.json();
      if (!response.ok)
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Invalid scenario. Check the grid and agent positions.",
        );
      if (controller.current !== abort) return;
      setSolution(data);
      if (dynamic) setScenario((s) => ({ ...s, agents: data.agents }));
      setTime(0);
      setPlaying(true);
    } catch (e) {
      if (!abort.signal.aborted)
        setError(
          e instanceof Error
            ? e.message
            : "Could not reach the planner. Start the backend server.",
        );
    } finally {
      if (controller.current === abort) setBusy(false);
    }
  }
  return {
    size,
    fleet,
    preset,
    scenario,
    solution,
    busy,
    error,
    time,
    setTime,
    playing,
    setPlaying,
    speed,
    setSpeed,
    configure,
    run,
    makespan,
  };
}
