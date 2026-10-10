"""The public demo accepts arithmetic and rejects executable Python syntax."""
from fastapi.testclient import TestClient
import pytest

import server


def invoke(expression):
    calculator = next(key for key, tool in server.tools.items() if tool.name == 'calculator')
    with TestClient(server.app) as client:
        return client.post('/v1/tool/' + calculator + '/invoke', json={
            'id': 1, 'method': 'invoke', 'params': {'expression': expression}
        })


@pytest.mark.parametrize(('expression', 'expected'), [
    ('2 + 2', 4), ('(2 + 3) * -4', -20), ('7 / 2', 3.5), ('7 // 2', 3),
    ('7 % 2', 1), ('2 ** -2', 0.25), ('9 ** 0.5', 3), ('  +2  ', 2),
])
def test_arithmetic(expression, expected):
    response = invoke(expression)
    assert response.status_code == 200
    assert response.json()['result']['result'] == expected


@pytest.mark.parametrize('expression', [
    '().__class__.__name__', '(1).__class__', '__import__("os")',
    '[x for x in (1, 2)]', '(lambda: 1)()', 'True', '"text"', '1j',
    '1 << 10', '1 / 0', '(-1) ** 0.5', '1e309', '10 ** 1000000',
    '1000000000000 * 1000000000000', '+' * 17 + '1', '1+' * 70 + '1',
    '1' * 257, '2 +', '', None, [], {},
])
def test_unsupported_or_unbounded_input_is_rejected(expression):
    response = invoke(expression)
    assert response.status_code == 400
    assert isinstance(response.json()['detail'], str)
