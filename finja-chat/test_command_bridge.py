#!/usr/bin/env python3
"""
======================================================================
                  Finja Command Bridge - Unit Tests
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Author: J. Apps (JohnV2002 / Sodakiller1)
  Version: 2.2.1
  Description: Unit tests for VPet command bridge server.

  ✨ New in 2.2.1:
    • Complete English documentation with docstrings
    • Improved test coverage and edge cases
    • Type hints for better IDE support
    • Consistent test naming conventions
    • Additional validation tests

  📜 Changelog 2.1.0:
    • Initial test suite for command bridge
    • Tests for GET and POST endpoints
    • Command persistence validation
    • Timestamp update verification

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

import pytest
import json
import time
from typing import Generator

from command_bridge import app, latest_command


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def client() -> Generator:
    """
    Create a test client for the Flask app.
    
    This fixture configures the app in testing mode and provides
    a test client for making HTTP requests.
    
    Yields:
        Flask test client instance
    """
    app.config['TESTING'] = True
    with app.test_client() as test_client:
        yield test_client


# ==============================================================================
# Test Suite
# ==============================================================================

class TestCommandBridge:
    """
    Test suite for command bridge endpoints.
    
    Tests the Flask HTTP bridge that connects the Twitch bot
    to the VPet Desktop Pet plugin.
    """

    def test_health_check_get_command(self, client) -> None:
        """
        Test GET /command endpoint returns initial state.
        
        Verifies that the endpoint is accessible and returns
        the expected JSON structure with command and timestamp.
        """
        response = client.get('/command')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'command' in data
        assert 'timestamp' in data

    def test_post_command_success(self, client) -> None:
        """
        Test POST /command with valid data.
        
        Verifies that a valid command is accepted and the
        server responds with success status and confirmation.
        """
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

    def test_post_command_no_json(self, client) -> None:
        """
        Test POST /command without JSON body.
        
        Verifies that the server properly rejects requests
        without a JSON payload and returns 415 Unsupported Media Type.
        """
        response = client.post('/command')
        
        # Flask returns 415 when Content-Type is not application/json
        assert response.status_code == 415

    def test_post_command_missing_command(self, client) -> None:
        """
        Test POST /command with missing command field.
        
        Verifies that the server validates the presence of
        the 'command' field in the JSON payload.
        """
        response = client.post(
            '/command',
            data=json.dumps({'wrong_field': 'value'}),
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['status'] == 'error'
        assert 'No command provided' in data['message']

    def test_post_command_empty_command(self, client) -> None:
        """
        Test POST /command with empty command string.
        
        Verifies that empty strings are rejected as invalid commands.
        """
        response = client.post(
            '/command',
            data=json.dumps({'command': ''}),
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['status'] == 'error'

    def test_post_command_null_command(self, client) -> None:
        """
        Test POST /command with null command value.
        
        Verifies that null values are rejected as invalid commands.
        """
        response = client.post(
            '/command',
            data=json.dumps({'command': None}),
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['status'] == 'error'

    def test_command_persistence(self, client) -> None:
        """
        Test that posted command persists and can be retrieved.
        
        Verifies the complete flow: POST a command, then GET it back
        and confirm it matches.
        """
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

    def test_command_timestamp_update(self, client) -> None:
        """
        Test that timestamp updates with new commands.
        
        Verifies that each new command gets a fresh timestamp,
        allowing VPet to detect new commands.
        """
        # Post first command
        client.post(
            '/command',
            data=json.dumps({'command': 'first'}),
            content_type='application/json'
        )
        response1 = client.get('/command')
        timestamp1 = json.loads(response1.data)['timestamp']

        # Wait to ensure timestamp difference
        time.sleep(1)

        # Post second command
        client.post(
            '/command',
            data=json.dumps({'command': 'second'}),
            content_type='application/json'
        )
        response2 = client.get('/command')
        timestamp2 = json.loads(response2.data)['timestamp']

        # Second timestamp should be newer
        assert timestamp2 > timestamp1

    def test_multiple_commands_override(self, client) -> None:
        """
        Test that new commands override old ones.
        
        Verifies that only the most recent command is stored,
        preventing VPet from executing stale commands.
        """
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

    def test_command_special_characters(self, client) -> None:
        """
        Test commands with special characters.
        
        Verifies that commands containing special characters
        are handled correctly.
        """
        special_commands = [
            'drink_water',
            'eat-food',
            'play.game',
            'jump!',
        ]

        for cmd in special_commands:
            response = client.post(
                '/command',
                data=json.dumps({'command': cmd}),
                content_type='application/json'
            )
            
            assert response.status_code == 200
            
            # Verify it was stored
            get_response = client.get('/command')
            data = json.loads(get_response.data)
            assert data['command'] == cmd

    def test_command_unicode(self, client) -> None:
        """
        Test commands with unicode characters.
        
        Verifies that unicode characters in commands are
        properly handled (though not recommended for VPet).
        """
        unicode_command = "drink🥤"
        
        response = client.post(
            '/command',
            data=json.dumps({'command': unicode_command}),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        
        # Verify unicode is preserved
        get_response = client.get('/command')
        data = json.loads(get_response.data)
        assert data['command'] == unicode_command

    def test_concurrent_command_updates(self, client) -> None:
        """
        Test rapid consecutive command updates.
        
        Verifies that the bridge handles rapid command updates
        correctly and maintains the last command.
        """
        rapid_commands = ['cmd1', 'cmd2', 'cmd3', 'cmd4', 'cmd5']
        
        # Send commands rapidly without delay
        for cmd in rapid_commands:
            client.post(
                '/command',
                data=json.dumps({'command': cmd}),
                content_type='application/json'
            )
        
        # Last command should win
        response = client.get('/command')
        data = json.loads(response.data)
        assert data['command'] == 'cmd5'

    def test_timestamp_is_unix_time(self, client) -> None:
        """
        Test that timestamp is valid Unix time.
        
        Verifies that timestamps are Unix timestamps
        (seconds since epoch) and reasonably current.
        """
        current_time = time.time()
        
        client.post(
            '/command',
            data=json.dumps({'command': 'test'}),
            content_type='application/json'
        )
        
        response = client.get('/command')
        data = json.loads(response.data)
        timestamp = data['timestamp']
        
        # Timestamp should be close to current time (within 10 seconds)
        assert abs(timestamp - current_time) < 10
        
        # Timestamp should be a reasonable Unix timestamp (after year 2000)
        assert timestamp > 946684800  # Jan 1, 2000


# ==============================================================================
# Test Runner
# ==============================================================================

if __name__ == '__main__':
    """
    Run tests with verbose output when executed directly.
    
    Usage:
        python test_command_bridge.py
        
    Or with pytest:
        pytest test_command_bridge.py -v
    """
    pytest.main([__file__, '-v', '--color=yes'])