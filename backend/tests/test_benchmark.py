"""Check benchmark methodology, failure handling, and process isolation."""
import csv
import multiprocessing as mp
import time
from pathlib import Path

import pytest

import benchmark
from app.models.schemas import Agent
from benchmark import (
    CollisionCounts, GenerationError, Instance, SolverResult, count_collisions,
    experiment_matrix, flood_fill, generate_instance, mean_std, result_fields,
    run_solver, summary_table, validate_paths, write_summary,
)


def stalled_worker(connection, solver, instance, timeout):
    """A deliberately uncooperative solver to verify hard parent-side cutoff."""
    connection.send(("STARTED", time.perf_counter()))
    time.sleep(10)


def test_matrix_sizes_and_parameter_coverage():
    assert len(experiment_matrix(True)) == 36
    full = experiment_matrix(False)
    assert len(full) == len(set(full)) == 360
    assert {fleet for _, fleet, _, _ in full} == {2, 4, 6, 8}
    assert {density for _, _, density, _ in full} == {0.1, 0.15, 0.2}
    assert {seed for _, _, _, seed in full} == set(range(10))


def test_full_matrix_generation_has_reachable_distinct_endpoints():
    for size, fleet, density, seed in experiment_matrix(False):
        instance = generate_instance(size, size, density, fleet, seed)
        assert len(instance.obstacles) == int(density * size * size)
        assert len(instance.agents) == fleet
        endpoints = [p for agent in instance.agents for p in (agent.start, agent.goal)]
        assert len(set(endpoints)) == 2 * fleet
        reachable = flood_fill(instance.agents[0].start, size, size, instance.obstacles)
        assert set(endpoints) <= reachable
        for agent in instance.agents:
            assert abs(agent.start[0] - agent.goal[0]) + abs(agent.start[1] - agent.goal[1]) >= size // 2
    assert generate_instance(12, 12, 0.15, 8, 17) == generate_instance(12, 12, 0.15, 8, 17)


@pytest.mark.parametrize('args', [(1, 12, 0.1, 2, 0), (12, 12, float('nan'), 2, 0), (12, 12, 1, 2, 0), (2, 2, 0.5, 2, 0)])
def test_invalid_generation_requests_are_bounded(args):
    with pytest.raises(ValueError):
        generate_instance(*args)


def test_collision_types_padding_and_pair_counting():
    assert count_collisions({'a': [(0, 0), (1, 0)], 'b': [(1, 0), (0, 0)]}) == CollisionCounts(0, 1)
    assert count_collisions({'a': [(0, 0)], 'b': [(2, 0), (1, 0), (0, 0), (0, 0)]}) == CollisionCounts(2, 0)
    assert count_collisions({str(i): [(0, 0), (0, 0)] for i in range(3)}) == CollisionCounts(6, 0)
    assert count_collisions({}) == CollisionCounts(0, 0)
    with pytest.raises(ValueError):
        count_collisions({'a': []})


def swap_instance():
    return Instance(4, 4, 0, 0, frozenset(), (
        Agent(id='a', start=(0, 0), goal=(1, 0)),
        Agent(id='b', start=(1, 0), goal=(0, 0)),
    ))


def test_real_solvers_headlessly_eliminate_swap_and_report_metrics():
    instance = swap_instance()
    base, cbs = run_solver(instance, 'baseline'), run_solver(instance, 'cbs')
    assert base.status == cbs.status == 'SOLVED'
    assert base.collisions == CollisionCounts(0, 1)
    assert cbs.collisions == CollisionCounts(0, 0)
    assert base.sic == 2 and cbs.sic == 4
    assert cbs.tree_nodes_expanded > 1 and base.tree_nodes_expanded is None
    assert 0 < cbs.time_ms < 5000


def test_no_path_is_distinguished_from_timeout():
    instance = Instance(4, 4, 0.25, 0, frozenset((1, y) for y in range(4)), (
        Agent(id='a', start=(0, 0), goal=(3, 0)),
        Agent(id='b', start=(3, 3), goal=(0, 3)),
    ))
    for solver in ('baseline', 'cbs'):
        result = run_solver(instance, solver)
        assert result.status == 'NO_PATH'
        assert result.sic is result.collisions is result.tree_nodes_expanded is None


def test_uncooperative_solver_is_terminated_and_reaped(monkeypatch):
    before = {p.pid for p in mp.active_children()}
    monkeypatch.setattr(benchmark, '_solver_worker', stalled_worker)
    result = run_solver(swap_instance(), 'cbs', timeout=0.03)
    assert result.status == 'TIMEOUT' and result.time_ms == 30
    assert result.collisions is None
    assert {p.pid for p in mp.active_children()} == before


def make_row(status='SOLVED', baseline_sic=10, cbs_sic=12, cbs_time=3):
    row = dict(grid_dim='12x12', agents=2, density=0.1, seed=0, generation_error='')
    row.update(result_fields('baseline', SolverResult('SOLVED', 1, baseline_sic, 8, CollisionCounts(1, 2))))
    cbs = SolverResult('SOLVED', cbs_time, cbs_sic, 9, CollisionCounts(0, 0), 5) if status == 'SOLVED' else SolverResult('TIMEOUT', 5000)
    row.update(result_fields('cbs', cbs))
    return row


def test_summary_uses_paired_costs_sample_sd_and_all_run_success_denominator(tmp_path):
    rows = [make_row(), make_row(baseline_sic=20, cbs_sic=22, cbs_time=5), make_row('TIMEOUT')]
    table = '\n'.join(summary_table(rows))
    assert '3 / 2' in table and '66.7%' in table
    assert '15.00%' in table  # Mean individual overheads: (20% + 10%) / 2.
    assert '4.000 ± 1.414' in table
    assert '3.00 / 0.00' in table and '1 / 0' in table
    path = tmp_path / 'summary.md'
    write_summary(rows, path, 'quick', 36, False)
    assert 'incomplete' in path.read_text() and 'swapping edge' in path.read_text()
    assert mean_std([]) == '—' and mean_std([1]) == '1.000 ± 0.000'
    failure = result_fields('cbs', SolverResult('TIMEOUT', 5000))
    assert failure['cbs_collisions'] is failure['cbs_sic'] is None


def test_path_validation_rejects_invalid_movements():
    instance = swap_instance()
    with pytest.raises(benchmark.BenchmarkError):
        validate_paths(instance, {'a': [(0, 0), (3, 0), (1, 0)], 'b': [(1, 0), (0, 0)]})


def test_cli_preserves_partial_outputs_on_unexpected_solver_error(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark, 'experiment_matrix', lambda quick: [(12, 2, 0.1, 0), (12, 2, 0.1, 1)])
    row = make_row()
    calls = 0
    def evaluate(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise benchmark.BenchmarkError('Injected solver failure')
        return row
    monkeypatch.setattr(benchmark, 'evaluate_instance', evaluate)
    assert benchmark.main(['--quick', '--output-dir', str(tmp_path)]) == 1
    with (tmp_path / 'benchmark_raw.csv').open() as stream:
        assert len(list(csv.DictReader(stream))) == 1
    assert '1/2' in (tmp_path / 'benchmark_summary.md').read_text()
    assert 'incomplete' in (tmp_path / 'benchmark_summary.md').read_text()
