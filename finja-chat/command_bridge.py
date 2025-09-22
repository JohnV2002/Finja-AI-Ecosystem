from flask import Flask, request, jsonify
from flask_cors import CORS
import time

# Eine einfache Flask-Anwendung als unsere "Befehls-Brücke"
app = Flask(__name__)
# Erlaubt Anfragen von deinem Bot (der auf einem anderen Port läuft)
CORS(app)

# Speichert den letzten Befehl im Arbeitsspeicher.
# Das Dictionary enthält den Befehl und einen Zeitstempel,
# damit VPet nicht denselben Befehl immer wieder ausführt.
latest_command = {
    "command": None,
    "timestamp": 0
}

# Endpunkt, um einen neuen Befehl vom Bot zu empfangen (POST)
@app.route('/command', methods=['POST'])
def receive_command():
    global latest_command
    data = request.json
    
    # KORREKTUR: Prüfen, ob der Request-Body valides JSON enthält.
    if not data:
        return jsonify({"status": "error", "message": "Request must be JSON"}), 400
        
    command = data.get('command')
    
    if command:
        print(f"Befehl empfangen: {command}")
        latest_command = {
            "command": command,
            "timestamp": int(time.time())
        }
        return jsonify({"status": "success", "command_received": command}), 200
    
    return jsonify({"status": "error", "message": "No command provided in payload"}), 400

# Endpunkt, damit das VPet-Plugin den letzten Befehl abfragen kann (GET)
@app.route('/command', methods=['GET'])
def get_command():
    return jsonify(latest_command)

if __name__ == '__main__':
    print("Starte Command Bridge auf http://127.0.0.1:8091 ...")
    # Starte den Server auf einem anderen Port als dein Spiel-Server
    app.run(host='127.0.0.1', port=8091)