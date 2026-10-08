import { useEffect, useRef } from "react";
import type { Scenario, Solution, Point } from "../types";
import { COLORS } from "../types";
interface Props {
  scenario: Scenario;
  solution: Solution | null;
  time: number;
  ribbons: boolean;
}
export function SimulationCanvas({ scenario, solution, time, ribbons }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const draw = () => {
      const safeTime = Math.max(0, time);
      const side = canvas.clientWidth,
        ratio = window.devicePixelRatio || 1;
      canvas.width = side * ratio;
      canvas.height = side * ratio;
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      const cell = side / scenario.width;
      const center = (p: Point): Point => [
        (p[0] + 0.5) * cell,
        (p[1] + 0.5) * cell,
      ];
      ctx.fillStyle = "#0c1420";
      ctx.fillRect(0, 0, side, side);
      ctx.strokeStyle = "#1b2939";
      ctx.lineWidth = 1;
      for (let i = 0; i <= scenario.width; i++) {
        ctx.beginPath();
        ctx.moveTo(i * cell, 0);
        ctx.lineTo(i * cell, side);
        ctx.moveTo(0, i * cell);
        ctx.lineTo(side, i * cell);
        ctx.stroke();
      }
      for (const [x, y] of scenario.obstacles) {
        ctx.fillStyle = "#344152";
        ctx.fillRect(x * cell + 3, y * cell + 3, cell - 6, cell - 6);
        ctx.fillStyle = "#435167";
        ctx.fillRect(x * cell + 3, y * cell + 3, cell - 6, 2);
      }
      if (solution?.obstacle && time <= (solution.obstacle_duration ?? 0)) {
        const [x, y] = solution.obstacle;
        ctx.fillStyle = "#f9731644";
        ctx.fillRect(x * cell + 2, y * cell + 2, cell - 4, cell - 4);
        ctx.strokeStyle = "#fb923c";
        ctx.lineWidth = 2;
        ctx.strokeRect(x * cell + 4, y * cell + 4, cell - 8, cell - 8);
        ctx.beginPath();
        ctx.moveTo(x * cell + 10, y * cell + 10);
        ctx.lineTo((x + 1) * cell - 10, (y + 1) * cell - 10);
        ctx.moveTo((x + 1) * cell - 10, y * cell + 10);
        ctx.lineTo(x * cell + 10, (y + 1) * cell - 10);
        ctx.stroke();
      }
      scenario.agents.forEach((agent, i) => {
        const color = COLORS[i];
        const path = solution?.paths[agent.id];
        ctx.strokeStyle = color;
        ctx.lineWidth = cell * 0.09;
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        if (path && ribbons) {
          ctx.globalAlpha = 0.23;
          ctx.beginPath();
          const tail = path.slice(
            Math.min(Math.floor(safeTime), path.length - 1),
          );
          tail.forEach((p, j) => {
            const [x, y] = center(p);
            if (j === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          });
          ctx.stroke();
          ctx.globalAlpha = 1;
        }
        const [sx, sy] = center(agent.start),
          [gx, gy] = center(agent.goal);
        ctx.globalAlpha = 0.55;
        ctx.strokeRect(
          sx - cell * 0.21,
          sy - cell * 0.21,
          cell * 0.42,
          cell * 0.42,
        );
        ctx.beginPath();
        ctx.arc(gx, gy, cell * 0.28, 0, Math.PI * 2);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(gx - 5, gy);
        ctx.lineTo(gx + 5, gy);
        ctx.moveTo(gx, gy - 5);
        ctx.lineTo(gx, gy + 5);
        ctx.stroke();
        ctx.globalAlpha = 1;
        let pos: Point = agent.start;
        if (path) {
          const a = path[Math.min(Math.floor(safeTime), path.length - 1)],
            b = path[Math.min(Math.floor(safeTime) + 1, path.length - 1)],
            f = safeTime % 1;
          pos = [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
        }
        const [x, y] = center(pos);
        ctx.fillStyle = color;
        ctx.shadowBlur = 16;
        ctx.shadowColor = color;
        ctx.beginPath();
        ctx.arc(x, y, cell * 0.22, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0;
        ctx.fillStyle = "#07121a";
        ctx.font = `bold ${Math.max(9, cell * 0.24)}px monospace`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(String(i + 1), x, y + 1);
      });
    };
    const frame = requestAnimationFrame(draw);
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [scenario, solution, time, ribbons]);
  return (
    <canvas
      ref={ref}
      className="simulation-canvas"
      role="img"
      aria-label={`${scenario.width} by ${scenario.height} grid with ${scenario.agents.length} agents, playback step ${time.toFixed(1)}`}
    />
  );
}
