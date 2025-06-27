import os
import sys
from fastapi.testclient import TestClient

# configure separate db for test
DB_PATH = os.path.join(os.path.dirname(__file__), 'snippets_test.db')
if os.path.exists(DB_PATH):
    os.unlink(DB_PATH)
os.environ['SNIPPET_DB'] = DB_PATH

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from server import app

client = TestClient(app)


def _tool_id(name: str) -> str:
    tools = client.get('/v1/tool').json()
    for item in tools:
        tid, info = next(iter(item.items()))
        if info['name'] == name:
            return tid
    raise AssertionError(f'tool {name} not found')





def test_embed_and_tools():
    resp = client.post('/api/embed', json={'html': '<b>Hi</b>', 'plain': 'Hi', 'sources': []})
    assert resp.status_code == 200
    data = resp.json()
    snip_id = data['id']
    assert data['sanitizedHtml']

    fetch_id = _tool_id('snippet.fetch')
    search_id = _tool_id('snippet.search')

    r = client.post(f'/v1/tool/{fetch_id}/invoke', json={'id': 1, 'jsonrpc': '2.0', 'method': 'fetch', 'params': {'id': snip_id}})
    assert r.status_code == 200
    fetched = r.json()['result']
    assert fetched['text'] == 'Hi'

    r = client.post(f'/v1/tool/{search_id}/invoke', json={'id': 1, 'jsonrpc': '2.0', 'method': 'search', 'params': {'query': 'Hi'}})
    assert r.status_code == 200
    results = r.json()['result']['results']
    assert any(s['id'] == snip_id for s in results)
