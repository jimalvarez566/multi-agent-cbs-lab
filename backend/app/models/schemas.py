from pydantic import BaseModel, Field, model_validator

Coordinate = tuple[int, int]

class Agent(BaseModel):
    id: str = Field(min_length=1, max_length=32)
    start: Coordinate
    goal: Coordinate

class SolveRequest(BaseModel):
    width: int = Field(ge=4, le=24)
    height: int = Field(ge=4, le=24)
    obstacles: list[Coordinate] = Field(default_factory=list, max_length=576)
    agents: list[Agent] = Field(min_length=2, max_length=6)

    @model_validator(mode='after')
    def validate_grid(self):
        positions = self.obstacles + [p for a in self.agents for p in (a.start, a.goal)]
        if any(not (0 <= x < self.width and 0 <= y < self.height) for x, y in positions):
            raise ValueError('Coordinates must lie inside the grid.')
        if len({a.id for a in self.agents}) != len(self.agents):
            raise ValueError('Agent IDs must be unique.')
        for attr in ('start', 'goal'):
            if len({getattr(a, attr) for a in self.agents}) != len(self.agents):
                raise ValueError(f'Agent {attr} positions must be unique.')
        if any(p in set(self.obstacles) for a in self.agents for p in (a.start, a.goal)):
            raise ValueError('Starts and goals cannot be obstacles.')
        return self

class DisruptRequest(SolveRequest):
    paths: dict[str, list[Coordinate]]
    current_time: int = Field(default=0, ge=0, le=10000)
    obstacle_duration: int = Field(default=4, ge=1, le=20)

    @model_validator(mode='after')
    def validate_paths(self):
        if set(self.paths) != {a.id for a in self.agents}:
            raise ValueError('Paths must match agent IDs exactly.')
        if sum(map(len, self.paths.values())) > 10000:
            raise ValueError('Paths exceed the supported size.')
        walls = set(self.obstacles)
        for a in self.agents:
            path = self.paths[a.id]
            if not path or path[0] != a.start or path[-1] != a.goal:
                raise ValueError('Each path must connect its agent start and goal.')
            for x, y in path:
                if not (0 <= x < self.width and 0 <= y < self.height) or (x, y) in walls:
                    raise ValueError('Paths must remain on traversable grid cells.')
            if any(abs(u[0]-v[0])+abs(u[1]-v[1]) > 1 for u, v in zip(path, path[1:])):
                raise ValueError('Path moves must be adjacent or WAIT.')
        return self
