"""L-15: identity forwarding and fail-closed mutation boundaries."""
import os
import sys
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault('CAPVSAR_PRECACHE_CHARTS', '0')
import app as planner

ROUTES = ['/api/update-database', '/api/sar/export-vsar']


def reply(payload, status=200):
    return Mock(status_code=status, json=Mock(return_value=payload))


@pytest.fixture
def client():
    return planner.app.test_client()


@pytest.mark.parametrize('route', ROUTES)
@pytest.mark.parametrize('origin', [None, 'http://localhost'])
def test_anonymous_cannot_borrow_environment_credentials(client, route, origin):
    with patch.dict(os.environ, {'CAPVSAR_TOKEN_INSTRUCTOR': 'server-secret',
                                 'CAPVSAR_TOKEN_BASE': ''}), \
         patch.object(planner.requests, 'get') as get, \
         patch.object(planner.requests, 'post') as post, \
         patch.object(planner, 'start_database_update') as update:
        response = client.post(route, json={}, headers={'Origin': origin} if origin else {})
    assert response.status_code == 401
    get.assert_not_called()
    post.assert_not_called()
    update.assert_not_called()


@pytest.mark.parametrize('route', ROUTES)
@pytest.mark.parametrize('identity,status', [
    ({'authenticated': False}, 401),
    ({'authenticated': False, 'dev_open': True, 'role': 'instructor'}, 401),
    ({'authenticated': True, 'role': 'base'}, 403),
    ({'authenticated': True, 'role': 'aircrew'}, 403),
    ({'authenticated': True, 'role': 'ground_team'}, 403),
])
def test_console_identity_controls_access(client, route, identity, status):
    with patch.object(planner.requests, 'get', return_value=reply(identity)), \
         patch.object(planner.requests, 'post') as post, \
         patch.object(planner, 'start_database_update') as update:
        response = client.post(route, json={}, headers={'Authorization': 'Bearer caller-session'})
    assert response.status_code == status
    post.assert_not_called()
    update.assert_not_called()


@pytest.mark.parametrize('upstream', [reply({}, 302), reply({}, 500), reply([]),
                                     planner.requests.Timeout('offline')])
def test_auth_unavailable_fails_closed(client, upstream):
    with patch.object(planner.requests, 'get', side_effect=[upstream]), \
         patch.object(planner, 'start_database_update') as update:
        response = client.post(ROUTES[0], json={}, headers={'X-CAPVSAR-Token': 'caller'})
    assert response.status_code == 503
    update.assert_not_called()


@pytest.mark.parametrize('origin', [None, 'https://localhost', 'https://evil.example'])
def test_cookie_requires_exact_origin(client, origin):
    client.set_cookie('capvsar_session', 'session-secret')
    with patch.object(planner.requests, 'get') as get:
        response = client.post(ROUTES[0], json={}, headers={'Origin': origin} if origin else {})
    assert response.status_code == 403
    get.assert_not_called()


@pytest.mark.parametrize('kind', ['cookie', 'bearer', 'token'])
def test_same_caller_identity_reaches_every_console_operation(client, kind):
    headers = {'Origin': 'http://localhost'}
    if kind == 'cookie':
        client.set_cookie('capvsar_session', 'caller-session')
        client.set_cookie('unrelated', 'never-forward')
        forwarded = {'Cookie': 'capvsar_session=caller-session'}
    elif kind == 'bearer':
        forwarded = {'Authorization': 'Bearer caller-session'}
        headers.update(forwarded)
    else:
        forwarded = {'X-CAPVSAR-Token': 'caller-token'}
        headers.update(forwarded)
    with patch.dict(os.environ, {'CAPVSAR_TOKEN_INSTRUCTOR': 'never-forward'}), \
         patch.object(planner.requests, 'get', side_effect=[
             reply({'authenticated': True, 'role': 'instructor'}), reply({'sortie': None})]) as get, \
         patch.object(planner.requests, 'post', return_value=reply({'id': 'scenario'})) as post, \
         patch.object(planner, 'point_elevation_ft', return_value=100), \
         patch.object(planner, '_allow_vsar_export', return_value=True):
        response = client.post(ROUTES[1], headers=headers,
                               json={'waypoints': [{'lat': 33, 'lon': -117}]})
    assert response.status_code == 200
    assert response.json['scenario_created'] is True
    assert post.call_count == 2
    for call in get.call_args_list + post.call_args_list:
        assert call.kwargs['headers'] == forwarded
        assert call.kwargs['allow_redirects'] is False


def test_authenticated_instructor_can_update(client):
    with patch.object(planner.requests, 'get', return_value=reply(
            {'authenticated': True, 'role': 'instructor'})), \
         patch.object(planner, 'start_database_update', return_value=True) as update:
        response = client.post(ROUTES[0], json={}, headers={'Authorization': 'Bearer session'})
    assert response.status_code == 200
    update.assert_called_once()


@pytest.mark.parametrize('status', [401, 403])
@pytest.mark.parametrize('operation', ['scenario', 'message'])
def test_console_rechecks_identity_at_write_time(client, status, operation):
    responses = [reply({}, status)] if operation == 'scenario' else [reply({'id': 'x'}), reply({}, status)]
    with patch.object(planner.requests, 'get', return_value=reply(
            {'authenticated': True, 'role': 'instructor'})), \
         patch.object(planner.requests, 'post', side_effect=responses) as post, \
         patch.object(planner, 'point_elevation_ft', return_value=100), \
         patch.object(planner, '_allow_vsar_export', return_value=True):
        response = client.post(ROUTES[1], headers={'Authorization': 'Bearer session'},
                               json={'waypoints': [{'lat': 33, 'lon': -117}]})
    assert response.status_code == status
    assert post.call_count == (1 if operation == 'scenario' else 2)
    if operation == 'message':
        assert response.json['scenario_created'] is True
        assert response.json['message_sent'] is False
