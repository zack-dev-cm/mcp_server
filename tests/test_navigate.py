import os
import sys
from fastapi.testclient import TestClient

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from server import app

client = TestClient(app)

def test_navigate_weather():
    resp = client.post('/api/navigate', json={'chat_history': 'What is the weather today?'})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert 'actions' in data
    # ensure at least one action predicted for weather
    assert any(act.get('tool') == 'weather.fake' for act in data.get('actions', []))

