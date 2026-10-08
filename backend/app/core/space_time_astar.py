"""Optimal space-time A*: edge times identify the arrival timestep."""
from collections.abc import Iterable
from dataclasses import dataclass
from heapq import heappop, heappush
from itertools import count
from time import perf_counter

Position = tuple[int, int]

@dataclass(frozen=True)
class Constraint:
    agent: str
    time: int
    position: Position
    source: Position | None = None
    positive: bool = False


def constraints_for_agent(constraints: Iterable[Constraint], agent: str) -> list[Constraint]:
    """A positive reservation excludes other agents from its vertices/edge."""
    relevant = []
    for c in constraints:
        if c.agent == agent:
            relevant.append(c)
        elif c.positive:
            relevant.append(Constraint(agent, c.time, c.position))
            if c.source is not None:
                relevant.append(Constraint(agent, c.time - 1, c.source))
                relevant.append(Constraint(agent, c.time, c.source, c.position))
    return relevant


def satisfies_constraints(path: list[Position], agent: str, constraints: Iterable[Constraint]) -> bool:
    def at(t):
        return path[min(t, len(path) - 1)]
    for c in constraints_for_agent(constraints, agent):
        event = at(c.time) == c.position
        if c.source is not None:
            event = event and at(c.time - 1) == c.source
        if event != c.positive:
            return False
    return True


def space_time_astar(
    width: int,
    height: int,
    obstacles: set[Position],
    start: Position,
    goal: Position,
    agent: str,
    constraints: Iterable[Constraint] = (),
    deadline: float | None = None,
) -> list[Position] | None:
    relevant = constraints_for_agent(constraints, agent)
    vertices = {(c.position, c.time) for c in relevant if c.source is None and not c.positive}
    edges = {(c.source, c.position, c.time) for c in relevant if c.source is not None and not c.positive}
    required: dict[int, Position] = {}
    for c in relevant:
        if not c.positive:
            continue
        endpoints = [(c.time, c.position)]
        if c.source is not None:
            endpoints.append((c.time - 1, c.source))
        for t, pos in endpoints:
            if t in required and required[t] != pos:
                return None
            required[t] = pos
    if 0 in required and required[0] != start:
        return None
    if (start, 0) in vertices or start in obstacles or goal in obstacles:
        return None
    # After the last constraint, a simple spatial route needs at most |V|-1 steps.
    last_time = max((c.time for c in relevant), default=0)
    horizon = last_time + width * height
    serial = count()
    heuristic = lambda p: abs(p[0] - goal[0]) + abs(p[1] - goal[1])
    queue = [(heuristic(start), 0, next(serial), start)]
    parent = {(start, 0): None}
    expanded = 0
    while queue:
        expanded += 1
        if expanded % 128 == 0 and deadline is not None and perf_counter() > deadline:
            raise TimeoutError('Low-level planning deadline reached.')
        _, t, _, pos = heappop(queue)
        # Agents stay at their goal forever. Do not terminate before a future
        # goal vertex constraint or goal-wait edge constraint has been satisfied.
        future_block = any(c.time > t and not c.positive and c.position == goal and
                           (c.source is None or c.source == goal) for c in relevant)
        future_block = future_block or any(rt > t and rp != goal for rt, rp in required.items())
        if pos == goal and not future_block:
            path = []
            state = (pos, t)
            while state is not None:
                path.append(state[0])
                state = parent[state]
            return path[::-1]
        if t >= horizon:
            continue
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0), (0, 0)):
            nxt = (pos[0] + dx, pos[1] + dy)
            nt = t + 1
            state = (nxt, nt)
            if not (0 <= nxt[0] < width and 0 <= nxt[1] < height):
                continue
            if nxt in obstacles or (nxt, nt) in vertices or (pos, nxt, nt) in edges:
                continue
            if nt in required and required[nt] != nxt:
                continue
            if state in parent:
                continue
            parent[state] = (pos, t)
            heappush(queue, (nt + heuristic(nxt), nt, next(serial), nxt))
    return None
