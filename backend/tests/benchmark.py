"""Headless, reproducible MAPF experiments; run directly from any directory.

The full matrix has 360 instances; quick mode has 36. Each solver executes in
an isolated spawned process with a hard five-second execution budget. Process
startup, instance generation, collision validation, and IPC are excluded from
reported solver latency. No FastAPI, frontend, or rendering modules are used.
"""
from __future__ import annotations

import argparse
import csv
import math
import multiprocessing as mp
import platform
import random
import sys
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations, product
from pathlib import Path
from statistics import mean, stdev
from typing import Any, Iterable, Literal, Mapping, Sequence

# Direct script execution places tests/, not backend/, on sys.path.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.baseline_astar import independent_paths
from app.core.cbs import PlanningError, solve_cbs
from app.models.schemas import Agent

Point = tuple[int, int]
Paths = Mapping[str, Sequence[Point]]
SolverName = Literal["baseline", "cbs"]
Status = Literal["SOLVED", "TIMEOUT", "NO_PATH"]
TIMEOUT_SECONDS = 5.0
DENSITIES = (0.10, 0.15, 0.20)
CSV_FIELDS = (
    "grid_dim", "agents", "density", "seed", "obstacle_count", "actual_density",
    "baseline_time_ms", "baseline_sic", "baseline_makespan", "baseline_collisions",
    "baseline_vertex_conflicts", "baseline_edge_conflicts", "baseline_status", "baseline_error",
    "cbs_time_ms", "cbs_sic", "cbs_makespan", "cbs_collisions",
    "cbs_vertex_conflicts", "cbs_edge_conflicts", "cbs_tree_nodes_expanded",
    "cbs_status", "cbs_error", "generation_error",
)


class GenerationError(ValueError):
    """No valid endpoint assignment was found within bounded sampling."""


class BenchmarkError(RuntimeError):
    """An unexpected solver failure or invalid solution must not masquerade as NO_PATH."""


@dataclass(frozen=True)
class Instance:
    width: int
    height: int
    density: float
    seed: int
    obstacles: frozenset[Point]
    agents: tuple[Agent, ...]


@dataclass(frozen=True)
class CollisionCounts:
    vertex_conflicts: int
    edge_conflicts: int

    @property
    def total(self) -> int:
        return self.vertex_conflicts + self.edge_conflicts


@dataclass(frozen=True)
class SolverResult:
    status: Status
    time_ms: float | None = None
    sic: int | None = None
    makespan: int | None = None
    collisions: CollisionCounts | None = None
    tree_nodes_expanded: int | None = None
    error: str = ""


def neighbors(point: Point, width: int, height: int) -> Iterable[Point]:
    x, y = point
    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        nxt = x + dx, y + dy
        if 0 <= nxt[0] < width and 0 <= nxt[1] < height:
            yield nxt


def flood_fill(start: Point, width: int, height: int, obstacles: frozenset[Point]) -> set[Point]:
    """Return the entire traversable connected component containing start."""
    if start in obstacles:
        return set()
    visited = {start}
    queue = deque([start])
    while queue:
        for nxt in neighbors(queue.popleft(), width, height):
            if nxt not in obstacles and nxt not in visited:
                visited.add(nxt)
                queue.append(nxt)
    return visited


def generate_instance(width: int, height: int, density: float, num_agents: int, seed: int) -> Instance:
    """Sample obstacles and globally distinct endpoints in a connected component.

    Exactly floor(density * area) obstacles are sampled. Obstacle layouts and
    endpoint assignments are retried deterministically if the requested fleet
    cannot fit. All endpoints share a component; reachability does not imply
    that a simultaneous collision-free MAPF solution exists.
    """
    if width < 2 or height < 2 or not math.isfinite(density) or not 0 <= density < 1:
        raise ValueError("Dimensions must be at least 2 and density must lie in [0, 1).")
    if num_agents < 1 or 2 * num_agents > width * height - math.floor(density * width * height):
        raise GenerationError("Not enough free cells for globally distinct starts and goals.")
    rng = random.Random(seed)
    cells = [(x, y) for y in range(height) for x in range(width)]
    min_distance = max(1, min(width, height) // 2)
    for _ in range(100):
        obstacles = frozenset(rng.sample(cells, math.floor(density * len(cells))))
        remaining = set(cells) - obstacles
        largest: set[Point] = set()
        while remaining:
            component = flood_fill(min(remaining), width, height, obstacles)
            remaining.difference_update(component)
            if len(component) > len(largest):
                largest = component
        if len(largest) < 2 * num_agents:
            continue
        for _ in range(30):
            available = sorted(largest)
            agents = []
            for i in range(num_agents):
                starts = available.copy()
                rng.shuffle(starts)
                for start in starts:
                    goals = [p for p in available if abs(p[0] - start[0]) + abs(p[1] - start[1]) >= min_distance]
                    if goals:
                        goal = rng.choice(goals)
                        agents.append(Agent(id=f"A{i + 1}", start=start, goal=goal))
                        available.remove(start)
                        available.remove(goal)
                        break
                else:
                    break
            if len(agents) == num_agents:
                return Instance(width, height, density, seed, obstacles, tuple(agents))
    raise GenerationError("Unable to sample reachable, well-separated endpoints after 100 layouts.")


def count_collisions(paths: Paths) -> CollisionCounts:
    """Count pair/timestep events; agents remain at their goal after arrival.

    Swapping edges are counted once per pair per transition t -> t+1.
    This validator is independent of CBS's own conflict detector.
    """
    if any(not path for path in paths.values()):
        raise ValueError("Cannot validate an empty path.")
    vertex = edge = 0
    horizon = max((len(p) for p in paths.values()), default=0)
    for first, second in combinations(paths.values(), 2):
        for t in range(horizon):
            a = first[min(t, len(first) - 1)]
            b = second[min(t, len(second) - 1)]
            if a == b:
                vertex += 1
            if t + 1 < horizon:
                na = first[min(t + 1, len(first) - 1)]
                nb = second[min(t + 1, len(second) - 1)]
                if a != b and a == nb and b == na:
                    edge += 1
    return CollisionCounts(vertex, edge)


def validate_paths(instance: Instance, paths: Paths) -> None:
    """Reject solver regressions before publishing apparently valid statistics."""
    if set(paths) != {a.id for a in instance.agents}:
        raise BenchmarkError("Solver paths do not match the requested fleet.")
    for agent in instance.agents:
        path = paths[agent.id]
        if not path or path[0] != agent.start or path[-1] != agent.goal:
            raise BenchmarkError(f"Invalid endpoints for {agent.id}.")
        for x, y in path:
            if not (0 <= x < instance.width and 0 <= y < instance.height) or (x, y) in instance.obstacles:
                raise BenchmarkError(f"Invalid cell in path for {agent.id}.")
        if any(abs(a[0] - b[0]) + abs(a[1] - b[1]) > 1 for a, b in zip(path, path[1:])):
            raise BenchmarkError(f"Non-adjacent movement for {agent.id}.")


def _solver_worker(connection: Any, solver: SolverName, instance: Instance, timeout: float) -> None:
    """Send a start handshake, then only compact telemetry (never a full tree)."""
    try:
        connection.send(("STARTED", time.perf_counter()))
        began = time.perf_counter()
        expanded = None
        try:
            if solver == "baseline":
                paths, _ = independent_paths(instance.width, instance.height, set(instance.obstacles), instance.agents)
                if any(path is None for path in paths.values()):
                    connection.send(("RESULT", SolverResult("NO_PATH", (time.perf_counter() - began) * 1000,
                                                           error="At least one independent route is unreachable.")))
                    return
            else:
                # Benchmark scalability under a time budget rather than the
                # interactive API's separate 10,000-node safety cap.
                solution = solve_cbs(instance.width, instance.height, set(instance.obstacles), instance.agents,
                                     max_nodes=sys.maxsize, timeout=timeout)
                paths = solution["paths"]
                expanded = solution["expanded_nodes"]
        except PlanningError as error:
            duration = (time.perf_counter() - began) * 1000
            status: Status = "TIMEOUT" if "limit" in str(error).lower() else "NO_PATH"
            connection.send(("RESULT", SolverResult(status, min(duration, timeout * 1000) if status == "TIMEOUT" else duration, error=str(error))))
            return
        duration = (time.perf_counter() - began) * 1000
        if duration > timeout * 1000:
            connection.send(("RESULT", SolverResult("TIMEOUT", timeout * 1000, error="Execution deadline exceeded.")))
            return
        connection.send(("COMPLETED", duration))
        validate_paths(instance, paths)
        collisions = count_collisions(paths)
        if solver == "cbs" and collisions.total:
            raise BenchmarkError(f"CBS returned {collisions.total} collisions.")
        connection.send(("RESULT", SolverResult(
            "SOLVED", duration, sum(len(p) - 1 for p in paths.values()),
            max(len(p) - 1 for p in paths.values()), collisions, expanded,
        )))
    except Exception as error:
        connection.send(("ERROR", f"{type(error).__name__}: {error}"))
    finally:
        connection.close()


def run_solver(instance: Instance, solver: SolverName, timeout: float = TIMEOUT_SECONDS) -> SolverResult:
    """Terminate pathological calls even when the core's cooperative timer stalls.

    Startup gets a separate 30-second budget and is excluded from latency.
    A post-solver validation phase gets its own bounded grace period, so it
    cannot turn a valid under-budget solver call into a false timeout.
    """
    if solver not in ("baseline", "cbs") or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("A known solver and positive finite timeout are required.")
    context = mp.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    worker = context.Process(target=_solver_worker, args=(send, solver, instance, timeout), daemon=True)
    try:
        worker.start()
        send.close()
        if not receive.poll(30):
            raise BenchmarkError(f"{solver} worker failed to start within 30 seconds.")
        tag, payload = receive.recv()
        if tag == "ERROR":
            raise BenchmarkError(f"{solver}: {payload}")
        if tag != "STARTED":
            raise BenchmarkError(f"Unexpected {solver} worker handshake: {tag}")
        deadline = payload + timeout
        if not receive.poll(max(0, deadline - time.perf_counter())):
            return SolverResult("TIMEOUT", timeout * 1000, error="Hard execution deadline exceeded; worker terminated.")
        tag, payload = receive.recv()
        if tag == "COMPLETED":
            if not receive.poll(5):
                raise BenchmarkError(f"{solver} validation failed to finish within 5 seconds.")
            tag, payload = receive.recv()
        if tag == "ERROR":
            raise BenchmarkError(f"{solver}: {payload}")
        if tag != "RESULT":
            raise BenchmarkError(f"Unexpected {solver} worker response: {tag}")
        return payload
    except EOFError as error:
        raise BenchmarkError(f"{solver} worker exited without reporting a result.") from error
    finally:
        if worker.pid is not None:
            if worker.is_alive():
                worker.terminate()
            worker.join(timeout=1)
            if worker.is_alive():
                worker.kill()
                worker.join(timeout=1)
            worker.close()
        receive.close()
        send.close()


def experiment_matrix(quick: bool) -> list[tuple[int, int, float, int]]:
    return list(product((12, 16) if quick else (12, 16, 24),
                        (2, 4) if quick else (2, 4, 6, 8), DENSITIES, range(3 if quick else 10)))


def result_fields(prefix: SolverName, result: SolverResult) -> dict[str, Any]:
    counts = result.collisions
    row = {
        f"{prefix}_time_ms": round(result.time_ms, 6) if result.time_ms is not None else None,
        f"{prefix}_sic": result.sic, f"{prefix}_makespan": result.makespan,
        f"{prefix}_collisions": counts.total if counts is not None else None,
        f"{prefix}_vertex_conflicts": counts.vertex_conflicts if counts is not None else None,
        f"{prefix}_edge_conflicts": counts.edge_conflicts if counts is not None else None,
        f"{prefix}_status": result.status, f"{prefix}_error": result.error,
    }
    if prefix == "cbs":
        row["cbs_tree_nodes_expanded"] = result.tree_nodes_expanded
    return row


def evaluate_instance(size: int, fleet: int, density: float, seed: int) -> dict[str, Any]:
    row: dict[str, Any] = {"grid_dim": f"{size}x{size}", "agents": fleet, "density": density, "seed": seed,
                           "generation_error": ""}
    try:
        instance = generate_instance(size, size, density, fleet, seed)
    except GenerationError as error:
        row["generation_error"] = str(error)
        for solver in ("baseline", "cbs"):
            row.update(result_fields(solver, SolverResult("NO_PATH", error="Instance generation failed.")))
        return row
    row.update(obstacle_count=len(instance.obstacles), actual_density=len(instance.obstacles) / (size * size))
    # Alternate order by seed to reduce systematic warm-cache/order effects.
    order: tuple[SolverName, SolverName] = ("baseline", "cbs") if seed % 2 == 0 else ("cbs", "baseline")
    for solver in order:
        row.update(result_fields(solver, run_solver(instance, solver)))
    return row


def mean_std(values: Sequence[float]) -> str:
    return f"{mean(values):.3f} ± {stdev(values) if len(values) > 1 else 0:.3f}" if values else "—"


def summary_table(rows: Sequence[dict[str, Any]], by_density: bool = False) -> list[str]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (row["grid_dim"], row["agents"], row["density"]) if by_density else (row["grid_dim"], row["agents"])
        groups[key].append(row)
    headers = ["Grid", "Fleet"] + (["Density"] if by_density else []) + [
        "Runs / paired", "Base time (ms) ± SD", "CBS time (ms) ± SD", "Base / CBS collisions (mean)",
        "Cost overhead", "CBS expanded (mean)", "CBS success", "CBS timeouts / no path",
    ]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for key, group in sorted(groups.items(), key=lambda item: (int(item[0][0].split("x")[0]), *item[0][1:])):
        solved = [r for r in group if r["cbs_status"] == "SOLVED"]
        paired = [r for r in solved if r["baseline_status"] == "SOLVED"]
        base_times = [r["baseline_time_ms"] for r in group if r["baseline_status"] == "SOLVED"]
        cbs_times = [r["cbs_time_ms"] for r in solved]
        collisions = f"{mean([r['baseline_collisions'] for r in paired]):.2f} / {mean([r['cbs_collisions'] for r in paired]):.2f}" if paired else "—"
        overheads = [100 * (r["cbs_sic"] - r["baseline_sic"]) / r["baseline_sic"] for r in paired if r["baseline_sic"] > 0]
        nodes = f"{mean([r['cbs_tree_nodes_expanded'] for r in solved]):.2f}" if solved else "—"
        cells = [str(key[0]), str(key[1])] + ([f"{key[2]:.0%}"] if by_density else []) + [
            f"{len(group)} / {len(paired)}", mean_std(base_times), mean_std(cbs_times), collisions,
            f"{mean(overheads):.2f}%" if overheads else "—", nodes,
            f"{100 * len(solved) / len(group):.1f}%",
            f"{sum(r['cbs_status'] == 'TIMEOUT' for r in group)} / {sum(r['cbs_status'] == 'NO_PATH' for r in group)}",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def write_summary(rows: Sequence[dict[str, Any]], path: Path, mode: str, expected: int, complete: bool) -> None:
    solved = [r for r in rows if r["cbs_status"] == "SOLVED"]
    paired = [r for r in solved if r["baseline_status"] == "SOLVED"]
    baseline_collisions = sum(r["baseline_collisions"] for r in paired)
    vertices = sum(r["baseline_vertex_conflicts"] for r in paired)
    edges = sum(r["baseline_edge_conflicts"] for r in paired)
    lines = [
        "# Headless MAPF benchmark", "",
        f"- Mode: **{mode}**; completed **{len(rows)}/{expected}** instances; run {'complete' if complete else 'incomplete' }.",
        f"- Generated at: {datetime.now(timezone.utc).isoformat(timespec='seconds')} (UTC).",
        f"- Python: {platform.python_version()}; platform: {platform.platform()}; CPU: {platform.machine()}.",
        f"- Solver execution limit: {TIMEOUT_SECONDS:.1f} s each; independent spawned processes, serial experiments.",
        "- Seeds: 0–2 in quick mode; 0–9 in full mode. Densities: 10%, 15%, 20%.",
        "- Eight-agent experiments call the core directly, bypassing the six-agent API/UI limit.",
        "", "## Collision elimination", "",
        f"On **{len(paired)} paired successful runs**, Independent A* produced **{baseline_collisions}** pair/timestep conflicts "
        f"(**{vertices} vertex**, **{edges} swapping edge**); CBS produced **{sum(r['cbs_collisions'] for r in paired)}**.",
        "This is empirical evidence on sampled instances, not a proof for all MAPF problems.",
        "", "## Grid and fleet aggregates", "", *summary_table(rows),
        "", "## Obstacle density breakdown", "", *summary_table(rows, by_density=True),
        "", "## Measurement and interpretation", "",
        "- Latency is measured with time.perf_counter around the full core solver call. Startup, generation, IPC and validation are excluded.",
        "- Time columns and expanded-node means include successful runs only. Timeout observations are censored at the budget; see raw CSV and status counts.",
        "- Collision means and SIC overhead use paired successful runs only. Overhead is the mean of per-run ((CBS SIC − baseline SIC) / baseline SIC) × 100.",
        "- SD is the sample standard deviation (n−1); a singleton reports zero. Missing values are — in tables and empty cells in CSV, never artificial zeros.",
        "- Success rate uses all attempted instances in the group. Generation failures are recorded as NO_PATH with generation_error and no latency/cost metrics.",
        "- Starts and goals are globally distinct, at least min(width,height)//2 Manhattan steps apart, and in the same BFS-connected component.",
        "- Individual reachability does not guarantee joint solvability. NO_PATH means proven search exhaustion/unreachable route; TIMEOUT means the budget prevented a conclusion.",
        "- The interactive node cap is disabled for benchmarking. Expansion counts refer to popped high-level CT nodes; counts on failed runs are unavailable and left blank.",
        "- Agents stay at goals through the fleet makespan. Conflicts count each colliding pair at each timestep, including persistent goal occupancy; stationary overlaps are not swaps.",
        "- No best-of-seed selection is performed. Solver order alternates by seed. Aggregates across densities weight every attempted instance equally.",
        "- Unexpected worker failures or invalid trajectories abort with a nonzero exit code, preserving CSV rows and marking this summary incomplete.",
        "", f"Generation failures: {sum(bool(r['generation_error']) for r in rows)}. "
        f"Baseline timeouts: {sum(r['baseline_status'] == 'TIMEOUT' for r in rows)}. "
        f"Baseline no-path results: {sum(r['baseline_status'] == 'NO_PATH' for r in rows)}.", "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--quick", action="store_true", help="36 runs: 12/16 grids, 2/4 agents, all densities, 3 seeds.")
    modes.add_argument("--full", action="store_true", help="360 runs: full matrix with 10 seeds (default).")
    parser.add_argument("--output-dir", type=Path, default=BACKEND_DIR / "benchmark_results", help="CSV/Markdown destination (overwrites previous outputs).")
    args = parser.parse_args(argv)
    matrix = experiment_matrix(args.quick)
    mode = "quick" if args.quick else "full"
    output = args.output_dir.expanduser().resolve()
    rows: list[dict[str, Any]] = []
    complete = False
    exit_code = 0
    try:
        output.mkdir(parents=True, exist_ok=True)
        with (output / "benchmark_raw.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
            writer.writeheader()
            print(f"MAPF {mode}: {len(matrix)} instances; {TIMEOUT_SECONDS:.1f}s budget per solver. Output: {output}", flush=True)
            for index, (size, fleet, density, seed) in enumerate(matrix, 1):
                row = evaluate_instance(size, fleet, density, seed)
                writer.writerow(row)
                stream.flush()  # Preserve completed experiments on interruption.
                rows.append(row)
                def display(prefix: SolverName) -> str:
                    latency = row[f"{prefix}_time_ms"]
                    duration = f"{latency:.3f}ms" if latency is not None else "—"
                    collisions = row[f"{prefix}_collisions"]
                    return f"{row[f'{prefix}_status']} {duration}, {collisions if collisions is not None else '—'} collisions"
                print(f"[Instance {index}/{len(matrix)}] {size}x{size} | {fleet} Agents | Density {density:.0%} | Seed {seed} "
                      f"-> CBS: {display('cbs')} | Base: {display('baseline')}", flush=True)
            complete = True
    except KeyboardInterrupt:
        print("\nInterrupted; keeping completed CSV rows and a partial summary.", file=sys.stderr)
        exit_code = 130
    except (BenchmarkError, OSError, ValueError) as error:
        print(f"Benchmark failed: {error}", file=sys.stderr)
        exit_code = 1
    finally:
        if output.is_dir():
            try:
                write_summary(rows, output / "benchmark_summary.md", mode, len(matrix), complete)
            except OSError as error:
                print(f"Cannot write summary: {error}", file=sys.stderr)
                exit_code = 1
    if complete:
        print(f"Saved {output / 'benchmark_raw.csv'} and {output / 'benchmark_summary.md'}", flush=True)
    return exit_code


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
