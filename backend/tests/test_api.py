from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
SCENARIO = dict(width=4,height=4,obstacles=[],agents=[dict(id='a',start=[0,0],goal=[3,0]),dict(id='b',start=[3,0],goal=[0,0])])


def test_health_solve_and_disruption():
    assert client.get('/health').json() == {'status':'ok'}
    response = client.post('/api/solve', json=SCENARIO)
    assert response.status_code == 200
    r = response.json()
    assert r['metrics']['collisions'] == 0
    assert r['baseline']['metrics']['collisions'] > 0
    assert r['node_count'] == len(r['tree'])
    dynamic = client.post('/api/adversary/disrupt', json={**SCENARIO,'paths':r['paths'],'current_time':0})
    assert dynamic.status_code == 200
    assert dynamic.json()['metrics']['collisions'] == 0
    assert 'obstacle' in dynamic.json()


def test_schema_errors():
    for update in [dict(width=100), dict(obstacles=[[0,0]]), dict(agents=[SCENARIO['agents'][0]]*2),dict(obstacles=[[-1,0]])]:
        assert client.post('/api/solve',json={**SCENARIO,**update}).status_code == 422


def test_invalid_disruption_paths_and_collisions():
    r = client.post('/api/solve',json=SCENARIO).json()
    for paths in [{}, {'a':[], 'b':[]}, {**r['paths'], 'a':[[0,0],[3,0]]}]:
        assert client.post('/api/adversary/disrupt',json={**SCENARIO,'paths':paths}).status_code == 422
    bad = {'a':[[0,0],[1,0],[2,0],[3,0]],'b':[[3,0],[2,0],[1,0],[0,0]]}
    response = client.post('/api/adversary/disrupt',json={**SCENARIO,'paths':bad})
    assert response.status_code == 422 and 'collision-free' in response.json()['detail']


def test_unreachable_api_returns_actionable_error():
    response = client.post('/api/solve',json={**SCENARIO,'obstacles':[[1,y] for y in range(4)]})
    assert response.status_code == 422 and 'no route' in response.json()['detail']
