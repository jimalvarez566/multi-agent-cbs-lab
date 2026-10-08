"""Choose the most visited future cell and block it for a bounded interval."""
from collections import Counter
from .cbs import PlanningError, conflicts, position_at, solve_cbs
from .space_time_astar import Constraint
from ..models.schemas import Agent


def disrupt(request):
    if conflicts(request.paths):
        raise PlanningError('Dynamic replanning requires collision-free input paths.')
    occupied = {position_at(p, request.current_time) for p in request.paths.values()}
    protected = occupied | {a.goal for a in request.agents} | set(request.obstacles)
    traffic = Counter(pos for path in request.paths.values()
                      for pos in path[request.current_time+1:] if pos not in protected)
    if not traffic:
        raise PlanningError('No future bottleneck remains. Rewind playback and try again.')
    # Stable tie breaking makes identical API requests reproducible.
    obstacle = min(traffic, key=lambda pos: (-traffic[pos], pos))
    agents = [Agent(id=a.id, start=position_at(request.paths[a.id], request.current_time), goal=a.goal)
              for a in request.agents]
    constraints = [Constraint(a.id, t, obstacle) for a in agents
                   for t in range(1, request.obstacle_duration+1)]
    result = solve_cbs(request.width, request.height, set(request.obstacles), agents, constraints)
    result.update(obstacle=obstacle, obstacle_duration=request.obstacle_duration,
                  traffic_score=traffic[obstacle], agents=agents)
    return result
