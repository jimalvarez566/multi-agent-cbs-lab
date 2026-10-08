import type { Agent, Point, Scenario } from "./types";
export type Preset = "Narrow Hallway" | "Crossroad Bottleneck" | "Random Grid";
export function createScenario(
  size: number,
  fleet: number,
  preset: Preset,
): Scenario {
  const middle = Math.floor(size / 2);
  const agents: Agent[] = Array.from({ length: fleet }, (_, i) => ({
    id: `A${i + 1}`,
    start: [i % 2 === 0 ? 1 : size - 2, i + 1],
    goal: [i % 2 === 0 ? size - 2 : 1, fleet - i],
  }));
  const obstacles: Point[] = [];
  const protectedCells = new Set(
    agents.flatMap((a) => [a.start.join(","), a.goal.join(",")]),
  );
  for (let y = 0; y < size; y++)
    for (let x = 0; x < size; x++) {
      let wall = false;
      if (preset === "Narrow Hallway")
        wall = x === middle && y !== middle && y !== middle - 1;
      if (preset === "Crossroad Bottleneck")
        wall =
          (x === middle && Math.abs(y - middle) > 1) ||
          (y === middle && x > 2 && x < size - 3 && Math.abs(x - middle) > 1);
      // Preserve a connected perimeter and horizontal escape corridors.
      if (preset === "Random Grid")
        wall =
          x > 2 &&
          x < size - 3 &&
          y > 1 &&
          y < size - 2 &&
          y % 3 !== 0 &&
          Math.random() < 0.23;
      if (wall && !protectedCells.has(`${x},${y}`)) obstacles.push([x, y]);
    }
  return { width: size, height: size, agents, obstacles };
}
