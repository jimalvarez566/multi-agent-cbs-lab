"""Independent spatial A*, deliberately ignoring the rest of the fleet."""
from heapq import heappush, heappop
from time import perf_counter


def astar(width, height, obstacles, start, goal):
    queue = [(0, start)]
    costs, parent = {start: 0}, {start: None}
    while queue:
        _, pos = heappop(queue)
        if pos == goal:
            path = []
            while pos is not None:
                path.append(pos)
                pos = parent[pos]
            return path[::-1]
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            nxt = pos[0] + dx, pos[1] + dy
            if not (0 <= nxt[0] < width and 0 <= nxt[1] < height) or nxt in obstacles:
                continue
            cost = costs[pos] + 1
            if cost < costs.get(nxt, float('inf')):
                costs[nxt], parent[nxt] = cost, pos
                h = abs(nxt[0] - goal[0]) + abs(nxt[1] - goal[1])
                heappush(queue, (cost + h, nxt))
    return None


def independent_paths(width, height, obstacles, agents):
    began = perf_counter()
    paths = {a.id: astar(width, height, obstacles, tuple(a.start), tuple(a.goal)) for a in agents}
    return paths, (perf_counter() - began) * 1000
