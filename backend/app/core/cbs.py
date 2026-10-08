"""Sum-of-costs optimal CBS with disjoint positive/negative splitting."""
from heapq import heappush, heappop
from itertools import combinations, count
from time import perf_counter
from .space_time_astar import Constraint, Position, space_time_astar, satisfies_constraints

Paths = dict[str, list[Position]]

class PlanningError(Exception):
    pass


def position_at(path: list[Position], t: int) -> Position:
    return path[min(t, len(path) - 1)]


def conflicts(paths: Paths) -> list[dict]:
    found = []
    for t in range(max(map(len, paths.values()), default=0)):
        for a, b in combinations(paths, 2):
            pa, pb = position_at(paths[a], t), position_at(paths[b], t)
            if pa == pb:
                found.append(dict(kind='vertex', time=t, agents=[a, b], position=pa))
            elif t and position_at(paths[a], t-1) == pb and position_at(paths[b], t-1) == pa:
                found.append(dict(kind='edge', time=t, agents=[a, b], position=pa,
                                  source=position_at(paths[a], t-1)))
    return found


def metrics(paths: Paths, duration: float, resolved: int = 0) -> dict:
    return dict(makespan=max((len(p)-1 for p in paths.values()), default=0),
                sum_of_costs=sum(len(p)-1 for p in paths.values()),
                collisions=len(conflicts(paths)), conflicts_resolved=resolved,
                execution_time_ms=round(duration, 3))


def solve_cbs(width, height, obstacles, agents, initial_constraints=(), max_nodes=10000, timeout=8):
    began = perf_counter()
    by_id = {a.id: a for a in agents}
    def plan(agent, constraints):
        a = by_id[agent]
        try:
            return space_time_astar(width, height, obstacles, tuple(a.start), tuple(a.goal), agent, constraints, deadline=began + timeout)
        except TimeoutError as error:
            raise PlanningError('Search time limit reached. Reduce fleet size or simplify the grid.') from error
    constraints = frozenset(initial_constraints)
    paths = {a.id: plan(a.id, constraints) for a in agents}
    if any(p is None for p in paths.values()):
        raise PlanningError('At least one agent has no route to its goal.')
    serial = count()
    root = next(serial)
    cost = lambda ps: sum(len(p)-1 for p in ps.values())
    queue = [(cost(paths), root, constraints, paths)]
    tree = [dict(id=root, parent_id=None, cost=cost(paths), status='queued', conflict=None)]
    seen = {constraints}
    expanded = resolved = 0
    while queue:
        if expanded >= max_nodes or perf_counter() - began > timeout:
            raise PlanningError('Search limit reached. Reduce fleet size or choose a less constrained grid.')
        _, node_id, constraints, paths = heappop(queue)
        expanded += 1
        collisions = conflicts(paths)
        tree[node_id]['status'] = 'expanded'
        if not collisions:
            tree[node_id]['status'] = 'solution'
            duration = (perf_counter()-began)*1000
            return dict(paths=paths, metrics=metrics(paths, duration, resolved),
                        tree=tree, node_count=len(tree), expanded_nodes=expanded, solve_duration_ms=round(duration, 3))
        conflict = collisions[0]
        tree[node_id]['conflict'] = conflict
        resolved += 1
        # Partition the solution space on one agent's exact conflict event:
        # either that event is forbidden, or it is mandatory. These two
        # branches cover all feasible solutions without overlapping.
        agent = conflict['agents'][0]
        t = conflict['time']
        for positive in (False, True):
            extra = Constraint(agent, t, position_at(paths[agent], t),
                               position_at(paths[agent], t-1) if conflict['kind'] == 'edge' else None,
                               positive=positive)
            child_constraints = constraints | {extra}
            if child_constraints in seen:
                continue
            seen.add(child_constraints)
            child_paths = dict(paths)
            affected = [a for a, path in paths.items() if not satisfies_constraints(path, a, [extra])]
            feasible = True
            # A positive branch retains the reserving agent's valid path.
            # Only agents violating its implied reservation are replanned.
            for affected_agent in affected:
                replacement = plan(affected_agent, child_constraints)
                if replacement is None:
                    feasible = False
                    break
                child_paths[affected_agent] = replacement
            child_id = next(serial)
            tree.append(dict(id=child_id, parent_id=node_id, cost=cost(child_paths),
                             status='queued' if feasible else 'infeasible', conflict=None,
                             replanned_agents=affected,
                             constraint=dict(agent=agent, time=t, position=extra.position,
                                             source=extra.source, positive=positive)))
            if feasible:
                heappush(queue, (cost(child_paths), child_id, child_constraints, child_paths))
    raise PlanningError('No collision-free solution exists for this scenario.')
