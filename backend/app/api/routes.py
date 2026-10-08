from fastapi import APIRouter, HTTPException
from ..models.schemas import SolveRequest, DisruptRequest
from ..core.cbs import PlanningError, metrics, solve_cbs
from ..core.baseline_astar import independent_paths
from ..core.adversary import disrupt

router = APIRouter(prefix='/api')

@router.post('/solve')
def solve(request: SolveRequest):
    try:
        result = solve_cbs(request.width, request.height, set(request.obstacles), request.agents)
        baseline, duration = independent_paths(request.width, request.height, set(request.obstacles), request.agents)
        result['baseline'] = dict(paths=baseline, metrics=metrics(baseline, duration))
        return result
    except PlanningError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

@router.post('/adversary/disrupt')
def adversary(request: DisruptRequest):
    try:
        result = disrupt(request)
        baseline, duration = independent_paths(request.width, request.height, set(request.obstacles), result['agents'])
        result['baseline'] = dict(paths=baseline, metrics=metrics(baseline, duration))
        return result
    except PlanningError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
