import unittest
import os
import sys
import json
import time
import shutil

# Wir fügen die Unterordner dem Pfad hinzu, damit wir die Skripte dort finden
sys.path.append(os.path.join(os.getcwd(), 'RTLHilfe'))
sys.path.append(os.path.join(os.getcwd(), 'MDRHilfe'))

# Versuche die Module zu importieren. Wenn das schon fehlschlägt, wissen wir sofort Bescheid.
try:
    import webserver
    print("✅ webserver.py gefunden")
except ImportError as e:
    print(f"❌ FEHLER: webserver.py konnte nicht importiert werden: {e}")

try:
    import rtl_repeat_counter
    print("✅ RTLHilfe/rtl_repeat_counter.py gefunden")
except ImportError as e:
    print(f"❌ FEHLER: rtl_repeat_counter.py konnte nicht importiert werden. Pfade prüfen! {e}")


class TestFinjaSystem(unittest.TestCase):
    
    def setUp(self):
        """Wird VOR jedem Test ausgeführt. Wir bereiten eine sichere Test-Umgebung vor."""
        print("\n--- Starte Test ---")
        # Wir nutzen Dummy-Dateien, um deine echten Daten nicht zu überschreiben
        self.test_songs_db = "test_songs_kb.json"
        self.test_memory = "test_memory.json"
        
        # Erstelle eine leere Song-Datenbank für den Test
        with open(self.test_songs_db, 'w') as f:
            json.dump({}, f)

    def tearDown(self):
        """Wird NACH jedem Test ausgeführt. Aufräumen."""
        if os.path.exists(self.test_songs_db):
            os.remove(self.test_songs_db)
        if os.path.exists(self.test_memory):
            os.remove(self.test_memory)

    def test_01_file_structure(self):
        """Prüft, ob alle lebenswichtigen Ordner und Dateien da sind."""
        required_files = [
            "webserver.py",
            "SongsDB/songs_kb.json",
            "Memory/memory.json",
            "Memory/contexts.json",
            "RTLHilfe/rtl89_cdp_nowplaying.py",
            "start_server.bat"
        ]
        
        print("Prüfe Datei-Struktur...")
        missing = []
        for file_path in required_files:
            if not os.path.exists(file_path):
                missing.append(file_path)
        
        if missing:
            self.fail(f"Folgende wichtige Dateien fehlen: {missing}")
        else:
            print("✅ Datei-Struktur sieht gut aus.")

    def test_02_rtl_repeat_logic(self):
        """Testet die Logik des RTL Repeat Counters, ohne den Server zu starten."""
        print("Prüfe RTL Repeat Logik...")
        
        # Hinweis: Wir simulieren hier, was das Skript tun würde.
        # Da wir die Funktion 'check_repeat' o.ä. nicht direkt sehen, testen wir
        # ob wir das Modul laden und grundlegende Dinge tun können.
        
        # Wenn rtl_repeat_counter eine Funktion hat, die wir aufrufen können, wäre das hier der Ort.
        # Beispielannahme: Es gibt eine Funktion oder Klasse, die Wiederholungen zählt.
        
        if hasattr(rtl_repeat_counter, 'count_song'):
             # Hypothetischer Test, falls du die Funktion so umgebaut hast
             pass
        else:
             print("⚠️  Hinweis: rtl_repeat_counter scheint keine direkt testbare Funktion zu haben (läuft vielleicht nur als Skript).")
             print("   Tipp: Bau den Code in eine Funktion 'check_repeat(artist, title)' um, dann kann man ihn hier testen!")

    def test_03_webserver_config_loading(self):
        """Prüft, ob der Webserver die Config laden kann."""
        print("Prüfe Webserver Konfiguration...")
        # Wir schauen, ob die load_config Funktion (oder ähnlich) existiert
        if hasattr(webserver, 'load_config'):
            try:
                config = webserver.load_config()
                self.assertIsInstance(config, dict)
                print("✅ Config erfolgreich geladen.")
            except Exception as e:
                self.fail(f"Config konnte nicht geladen werden: {e}")
        else:
            # Fallback, falls die Funktion anders heißt
            print("⚠️  Konnte keine explizite 'load_config' Funktion finden. Prüfe manuell.")

    def test_04_artist_cleaning(self):
        """Testet, ob Interpreten-Namen sauber gemacht werden (falls Funktion vorhanden)."""
        # Viele deiner Skripte müssen Künstlernamen bereinigen. Testen wir das.
        raw_artist = "  Rihanna feat. Jay-Z  "
        expected = "Rihanna feat. Jay-Z" # oder wie auch immer deine Logik ist
        
        # Wenn webserver.py eine clean_string Funktion hat:
        if hasattr(webserver, 'clean_string'):
            result = webserver.clean_string(raw_artist)
            print(f"Clean String Test: '{raw_artist}' -> '{result}'")
            # Hier würdest du dein erwartetes Ergebnis prüfen
            # self.assertEqual(result.strip(), expected) 

if __name__ == '__main__':
    unittest.main()