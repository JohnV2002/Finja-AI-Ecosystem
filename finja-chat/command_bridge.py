#!/usr/bin/env python3
# ==============================================================================
#                          Finja VPet Command Bridge
# ==============================================================================
#
#   Project: Finja - Twitch Interactivity Suite
#   Author: J. Apps (JohnV2002 / Sodakiller1)
#   Version: 2.2.1
#   Description: HTTP bridge between Twitch bot and VPet Desktop Pet plugin.
#
#   ✨ New in 2.2.1:
#     • Complete English documentation
#     • Professional file header with version info
#     • Comprehensive inline comments for all functions
#     • Improved code organization and readability
#
#   📜 Changelog 2.2.0:
#     • Initial release of command bridge
#     • POST endpoint for receiving commands from bot
#     • GET endpoint for VPet plugin to poll commands
#     • Timestamp-based command deduplication
#
#   Architecture:
#     Bot (bot_merged.html) → HTTP POST → Command Bridge → HTTP GET → VPet
#
#   Endpoints:
#     POST /command - Receive command from bot
#     GET  /command - Retrieve latest command for VPet
#
#   Copyright (c) 2026 J. Apps
#   Licensed under the MIT License.
# ==============================================================================

from flask import Flask, request, jsonify
from flask_cors import CORS
import time

# ==============================================================================
# Flask Application Setup
# ==============================================================================

# Initialize Flask application as command bridge
app = Flask(__name__)

# Enable CORS to allow requests from bot running on different port
# This is necessary because the bot runs on a different origin
CORS(app)

# ==============================================================================
# Global State
# ==============================================================================

# In-memory storage for the latest command
# Contains the command string and Unix timestamp to prevent duplicate execution
# VPet plugin checks timestamp to determine if command is new
latest_command = {
    "command": None,      # Command string (e.g., "drink", "eat", "play")
    "timestamp": 0        # Unix timestamp of when command was received
}

# ==============================================================================
# API Endpoints
# ==============================================================================

@app.route('/command', methods=['POST'])
def receive_command():
    """
    Receives a command from the Twitch bot via HTTP POST.
    
    Expected JSON payload:
    {
        "command": "drink"  // Command to execute in VPet
    }
    
    Returns:
        200: Success with command confirmation
        400: Bad request (missing JSON or command field)
    
    Example:
        POST http://127.0.0.1:8091/command
        Body: {"command": "drink"}
        
        Response: {"status": "success", "command_received": "drink"}
    """
    global latest_command
    
    # Parse JSON from request body
    data = request.json
    
    # Validate that request contains valid JSON
    if not data:
        return jsonify({
            "status": "error",
            "message": "Request must be JSON"
        }), 400
    
    # Extract command from payload
    command = data.get('command')
    
    # Validate that command field exists and is not empty
    if command:
        print(f"Command received: {command}")
        
        # Update global state with new command and current timestamp
        latest_command = {
            "command": command,
            "timestamp": int(time.time())
        }
        
        return jsonify({
            "status": "success",
            "command_received": command
        }), 200
    
    # Return error if command field is missing
    return jsonify({
        "status": "error",
        "message": "No command provided in payload"
    }), 400


@app.route('/command', methods=['GET'])
def get_command():
    """
    Retrieves the latest command for VPet Desktop Pet plugin.
    
    VPet plugin polls this endpoint periodically to check for new commands.
    The timestamp helps VPet determine if the command is new or already executed.
    
    Returns:
        200: Always returns latest command state
    
    Response format:
    {
        "command": "drink",      // Latest command string or null
        "timestamp": 1704380400  // Unix timestamp or 0 if no command
    }
    
    Example:
        GET http://127.0.0.1:8091/command
        
        Response: {"command": "drink", "timestamp": 1704380400}
    """
    return jsonify(latest_command)

# ==============================================================================
# Application Entry Point
# ==============================================================================

if __name__ == '__main__':
    """
    Starts the Flask development server on localhost:8091.
    
    Configuration:
        Host: 127.0.0.1 (localhost only, not accessible from network)
        Port: 8091 (different from bot and other services)
        Debug: False (production mode for stability)
    
    Note:
        This is a simple in-memory bridge suitable for local development.
        For production, consider using a proper message queue or database.
    """
    print("Starting Command Bridge on http://127.0.0.1:8091 ...")
    print("Endpoints:")
    print("  POST /command - Receive commands from bot")
    print("  GET  /command - Retrieve commands for VPet")
    print("\nPress CTRL+C to stop the server.")
    
    # Start Flask development server
    # Note: Not suitable for production deployment
    # For production, use gunicorn or uwsgi
    app.run(host='127.0.0.1', port=8091, debug=False)