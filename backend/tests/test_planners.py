from heapq import heappop, heappush
from itertools import product
import pytest
from app.core.space_time_astar import Constraint, space_time_astar
from app.core.baseline_astar import astar
from app.core.cbs import PlanningError, conflicts, metrics, position_at, solve_cbs
from app.core.adversary import disrupt
from app.models.schemas import Agent, DisruptRequest


def agent(name, start, goal):
    return Agent(id=name, start=start, goal=goal)


def test_vertex_constraint_forces_wait():
    p = space_time_astar(3, 1, set(), (0, 0), (2, 0), 'a', [Constraint('a', 1, (1, 0))])
    assert p == [(0, 0), (0, 0), (1, 0), (2, 0)]


def test_directed_edge_constraint_and_other_agent_isolation():
    c = [Constraint('a', 1, (1, 0), (0, 0))]
    assert space_time_astar(2, 1, set(), (0, 0), (1, 0), 'a', c) == [(0, 0), (0, 0), (1, 0)]
    assert space_time_astar(2, 1, set(), (1, 0), (0, 0), 'a', c) == [(1, 0), (0, 0)]
    assert space_time_astar(2, 1, set(), (0, 0), (1, 0), 'b', c) == [(0, 0), (1, 0)]


def test_initial_and_unreachable_constraints():
    assert space_time_astar(2, 1, set(), (0, 0), (1, 0), 'a', [Constraint('a', 0, (0, 0))]) is None
    assert space_time_astar(3, 1, {(1, 0)}, (0, 0), (2, 0), 'a') is None
    assert astar(3, 1, {(1, 0)}, (0, 0), (2, 0)) is None


def test_future_goal_constraint_requires_leave_and_return():
    p = space_time_astar(2, 1, set(), (0, 0), (0, 0), 'a', [Constraint('a', 3, (0, 0))])
    assert p[-1] == (0, 0) and len(p) == 5 and p[3] != (0, 0)


def test_goal_wait_edge_and_irrelevant_future_edge():
    p = space_time_astar(2, 1, set(), (0, 0), (0, 0), 'a', [Constraint('a', 2, (0, 0), (0, 0))])
    assert not (p[1] == p[2] == (0, 0))
    assert space_time_astar(2, 1, set(), (0, 0), (0, 0), 'a', [Constraint('a', 2, (0, 0), (1, 0))]) == [(0, 0)]


def test_earliest_vertex_edge_and_persistent_goal_conflicts():
    assert conflicts({'a': [(0, 0), (1, 0)], 'b': [(2, 0), (1, 0)]})[0]['kind'] == 'vertex'
    c = conflicts({'a': [(0, 0), (1, 0)], 'b': [(1, 0), (0, 0)]})[0]
    assert c['kind'] == 'edge' and c['time'] == 1
    assert conflicts({'a': [(0, 0)], 'b': [(2, 0), (1, 0), (0, 0)]})[0]['time'] == 2


def assert_valid(result, agents, walls=set()):
    assert not conflicts(result['paths'])
    for a in agents:
        p = result['paths'][a.id]
        assert p[0] == a.start and p[-1] == a.goal
        assert not set(p) & walls
        assert all(abs(u[0]-v[0])+abs(u[1]-v[1]) <= 1 for u, v in zip(p, p[1:]))


def test_cbs_swap_detour_and_tree():
    agents = [agent('a', (0, 0), (1, 0)), agent('b', (1, 0), (0, 0))]
    r = solve_cbs(2, 2, set(), agents)
    assert_valid(r, agents)
    assert r['metrics']['sum_of_costs'] == 4
    assert r['tree'][0]['conflict']['kind'] == 'edge'
    assert r['tree'][-1]['id'] == len(r['tree'])-1
    assert sum(n['status'] == 'solution' for n in r['tree']) == 1


def test_unreachable_and_bounded_unsolvable_swap():
    agents = [agent('a', (0, 0), (1, 0)), agent('b', (1, 0), (0, 0))]
    with pytest.raises(PlanningError, match='limit'):
        solve_cbs(2, 1, set(), agents, max_nodes=20)
    with pytest.raises(PlanningError, match='no route'):
        solve_cbs(3, 1, {(1, 0)}, [agent('a', (0, 0), (2, 0))])


def joint_oracle(width, height, agents):
    """Exact joint Dijkstra with an absorbing completed state per agent.

    Every unfinished agent pays one per step; an agent can commit to staying
    at its goal, or leave it again. This is the same sum-of-costs objective.
    """
    goals = tuple(a.goal for a in agents)
    initial = (tuple(a.start for a in agents), tuple(False for _ in agents))
    queue = [(0, initial)]; best = {initial: 0}
    while queue:
        cost, (positions, done) = heappop(queue)
        if best[(positions, done)] != cost:
            continue
        if all(done):
            return cost
        options = []
        for i, (x, y) in enumerate(positions):
            if done[i]:
                options.append([(positions[i], True, 0)])
                continue
            moves = [((x+dx, y+dy), False, 1) for dx, dy in ((0,0),(1,0),(-1,0),(0,1),(0,-1))
                     if 0 <= x+dx < width and 0 <= y+dy < height]
            if positions[i] == goals[i]:
                moves.append((positions[i], True, 0))
            options.append(moves)
        for transition in product(*options):
            nxt = tuple(v[0] for v in transition)
            if len(set(nxt)) != len(nxt):
                continue
            if any(positions[i] == nxt[j] and positions[j] == nxt[i] for i in range(len(nxt)) for j in range(i+1,len(nxt))):
                continue
            state = (nxt, tuple(v[1] for v in transition)); nc = cost + sum(v[2] for v in transition)
            if nc < best.get(state, float('inf')):
                best[state] = nc; heappush(queue, (nc, state))


@pytest.mark.parametrize('starts,goals', [([(0,0),(1,0)],[(1,0),(0,0)]), ([(0,0),(2,0)],[(2,0),(0,0)]), ([(0,0),(0,1)],[(2,1),(2,0)]), ([(1,0),(0,0)],[(1,0),(2,0)]), ([(0,0),(2,1),(0,1)],[(2,1),(0,1),(0,0)])])
def test_cbs_sum_of_costs_matches_joint_oracle(starts, goals):
    agents = [agent(str(i), s, g) for i,(s,g) in enumerate(zip(starts,goals))]
    r = solve_cbs(3, 2, set(), agents)
    assert_valid(r, agents)
    assert r['metrics']['sum_of_costs'] == joint_oracle(3, 2, agents)


def test_dynamic_obstacle_expires_and_current_positions_are_preserved():
    agents = [agent('a',(0,0),(3,0)), agent('b',(0,3),(3,3))]
    paths = solve_cbs(4, 4, set(), agents)['paths']
    request = DisruptRequest(width=4,height=4,agents=agents,paths=paths,current_time=1,obstacle_duration=3)
    r = disrupt(request)
    assert_valid(r, r['agents'])
    for a in agents:
        p = r['paths'][a.id]
        assert p[0] == position_at(paths[a.id], 1)
        assert all(position_at(p, t) != r['obstacle'] for t in range(1,4))
    assert r['obstacle'] not in {a.goal for a in agents}
    with pytest.raises(PlanningError, match='No future'):
        disrupt(request.model_copy(update={'current_time': 100}))


def test_metrics_count_baseline_collisions():
    m = metrics({'a':[(0,0),(1,0)],'b':[(1,0),(0,0)]}, 1.23456)
    assert m == dict(makespan=1,sum_of_costs=2,collisions=1,conflicts_resolved=0,execution_time_ms=1.235)


def test_cbs_vertex_conflict_in_intersection():
    agents = [agent('a', (0, 1), (2, 1)), agent('b', (1, 0), (1, 2))]
    r = solve_cbs(3, 3, set(), agents)
    assert_valid(r, agents)
    assert r['tree'][0]['conflict']['kind'] == 'vertex'
    assert r['metrics']['sum_of_costs'] == 5


def test_cbs_stationary_agent_can_leave_goal_and_return():
    agents = [agent('a', (1, 0), (1, 0)), agent('b', (0, 0), (2, 0))]
    r = solve_cbs(3, 2, set(), agents)
    assert_valid(r, agents)
    assert r['metrics']['sum_of_costs'] == joint_oracle(3, 2, agents)


def test_low_level_search_honors_deadline():
    with pytest.raises(TimeoutError):
        space_time_astar(24, 24, {(12,y) for y in range(24)}, (0, 0), (23, 23), 'a', deadline=0)


def test_positive_vertex_and_edge_requirements():
    reservation = Constraint('a', 2, (1, 0), positive=True)
    p = space_time_astar(3, 2, set(), (0, 0), (2, 0), 'a', [reservation])
    assert p[2] == (1, 0)
    edge = Constraint('a', 2, (2, 0), (1, 0), positive=True)
    p = space_time_astar(3, 2, set(), (0, 0), (2, 0), 'a', [edge])
    assert p[1:3] == [(1, 0), (2, 0)]
    other = space_time_astar(3, 2, set(), (2, 0), (0, 0), 'b', [edge])
    assert position_at(other, 1) != (1, 0)
    assert position_at(other, 2) != (2, 0)
    assert not (other[1] == (2, 0) and other[2] == (1, 0))


def test_positive_future_constraint_prevents_premature_goal_termination():
    c = Constraint('a', 2, (1, 0), positive=True)
    p = space_time_astar(2, 1, set(), (0, 0), (0, 0), 'a', [c])
    assert p[2] == (1, 0) and p[-1] == (0, 0)
    impossible = [c, Constraint('a', 2, (0, 0), positive=True)]
    assert space_time_astar(2, 1, set(), (0, 0), (0, 0), 'a', impossible) is None


def test_disjoint_branches_and_only_affected_routes_replanned():
    agents = [agent('a',(0,1),(2,1)), agent('b',(1,0),(1,2)), agent('c',(3,0),(3,2))]
    r = solve_cbs(4, 3, set(), agents)
    children = [n for n in r['tree'] if n['parent_id'] == 0]
    assert len(children) == 2
    negative, positive = children
    assert negative['constraint']['positive'] is False
    assert positive['constraint']['positive'] is True
    assert negative['constraint']['agent'] == positive['constraint']['agent'] == 'a'
    assert negative['replanned_agents'] == ['a']
    assert positive['replanned_agents'] == ['b']
    assert_valid(r, agents)


def test_positive_reservation_replans_all_agents_in_triple_vertex_conflict():
    agents = [agent('a',(0,1),(2,1)), agent('b',(1,0),(1,2)), agent('c',(2,1),(0,1))]
    r = solve_cbs(3, 3, set(), agents)
    positive = next(n for n in r['tree'] if n['parent_id'] == 0 and n['constraint']['positive'])
    assert positive['replanned_agents'] == ['b', 'c']
    assert_valid(r, agents)


def test_exhaustive_two_agent_optimality_on_two_by_two_grid():
    from itertools import permutations
    cells = [(0,0),(0,1),(1,0),(1,1)]
    for starts in permutations(cells, 2):
        for goals in permutations(cells, 2):
            agents = [agent(str(i),s,g) for i,(s,g) in enumerate(zip(starts,goals))]
            result = solve_cbs(2,2,set(),agents)
            assert_valid(result, agents)
            assert result['metrics']['sum_of_costs'] == joint_oracle(2,2,agents)
