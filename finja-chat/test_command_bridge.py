"""
Unit tests for command_bridge.py
Tests the Flask command bridge server for VPet integration
"""
import pytest
import json
import time
from command_bridge import app, latest_command


@pytest.fixture
def client():
    """Create a test client for the Flask app"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


class TestCommandBridge:
    """Test suite for command bridge endpoints"""

    def test_health_check_get_command(self, client):
        """Test GET /command endpoint returns initial state"""
        response = client.get('/command')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'command' in data
        assert 'timestamp' in data

    def test_post_command_success(self, client):
        """Test POST /command with valid data"""
        test_command = "drink"
        response = client.post(
            '/command',
            data=json.dumps({'command': test_command}),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'success'
        assert data['command_received'] == test_command

    def test_post_command_no_json(self, client):
        """Test POST /command without JSON body"""
        response = client.post('/command')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['status'] == 'error'
        assert 'JSON' in data['message']

    def test_post_command_missing_command(self, client):
        """Test POST /command with missing command field"""
        response = client.post(
            '/command',
            data=json.dumps({'wrong_field': 'value'}),
            content_type='application/json'
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['status'] == 'error'
        assert 'No command provided' in data['message']

    def test_command_persistence(self, client):
        """Test that posted command persists and can be retrieved"""
        test_command = "jump"

        # Post a command
        post_response = client.post(
            '/command',
            data=json.dumps({'command': test_command}),
            content_type='application/json'
        )
        assert post_response.status_code == 200

        # Retrieve the command
        get_response = client.get('/command')
        assert get_response.status_code == 200
        data = json.loads(get_response.data)
        assert data['command'] == test_command
        assert data['timestamp'] > 0

    def test_command_timestamp_update(self, client):
        """Test that timestamp updates with new commands"""
        # Post first command
        client.post(
            '/command',
            data=json.dumps({'command': 'first'}),
            content_type='application/json'
        )
        response1 = client.get('/command')
        timestamp1 = json.loads(response1.data)['timestamp']

        time.sleep(1)

        # Post second command
        client.post(
            '/command',
            data=json.dumps({'command': 'second'}),
            content_type='application/json'
        )
        response2 = client.get('/command')
        timestamp2 = json.loads(response2.data)['timestamp']

        assert timestamp2 > timestamp1

    def test_multiple_commands_override(self, client):
        """Test that new commands override old ones"""
        commands = ['drink', 'eat', 'sleep', 'jump']

        for cmd in commands:
            client.post(
                '/command',
                data=json.dumps({'command': cmd}),
                content_type='application/json'
            )

        # Only the last command should be stored
        response = client.get('/command')
        data = json.loads(response.data)
        assert data['command'] == 'jump'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
