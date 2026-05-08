import speech_recognition as sr
import os
import sys
from faster_whisper import WhisperModel

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import YourAIUnexpectedError, YourAISystemError

from config import (
    WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE,
    WHISPER_PHRASE_TIME_LIMIT, WHISPER_BEAM_SIZE,
    WHISPER_AMBIENT_NOISE_DURATION
)

# Aliases für kürzeren Code
MODEL_SIZE = WHISPER_MODEL_SIZE
DEVICE = WHISPER_DEVICE
COMPUTE_TYPE = WHISPER_COMPUTE_TYPE

log("EARS", f"⏳ Loading Whisper Model '{MODEL_SIZE}' on {DEVICE}...", Fore.CYAN)
try:
    model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
    log("EARS", "✅ Whisper ready (English Mode)!", Fore.GREEN)
except Exception as e:
    err = YourAISystemError(message="Whisper Modell konnte nicht geladen werden (z.B. Out of Memory).", cause=e, module="ears_init")
    log_exception("EARS", err)
    model = None

def listen():
    """
    Listens to audio and uses local Whisper for English recognition.
    """
    if model is None:
        return input("Fallback (No Whisper) - Type here: ")

    recognizer = sr.Recognizer()
    
    try:
        with sr.Microphone() as source:
            log("EARS", "🎤 AltPersona/YourAI is listening... (Speak English!)", Fore.MAGENTA)
            recognizer.adjust_for_ambient_noise(source, duration=WHISPER_AMBIENT_NOISE_DURATION)
            
            try:
                # Aufnahme
                audio = recognizer.listen(source, timeout=None, phrase_time_limit=WHISPER_PHRASE_TIME_LIMIT)
                log("EARS", "⏳ Thinking (Transcribing)...", Fore.YELLOW)
                
                with open("temp_speech.wav", "wb") as f:
                    f.write(audio.get_wav_data())
                
                # WICHTIG: language="en" für Englisch
                segments, info = model.transcribe("temp_speech.wav", beam_size=WHISPER_BEAM_SIZE, language="en")
                
                text = " ".join([segment.text for segment in segments]).strip()
                
                try: 
                    os.remove("temp_speech.wav")
                except OSError as clean_err: 
                    log("EARS", f"⚠️ cleanup failed (temp_speech.wav): {clean_err}", Fore.YELLOW)
                
                if not text:
                    log("EARS", "🤷‍♀️ Heard silence.", Fore.LIGHTBLACK_EX)
                    return None
                    
                log("EARS", f"🗣️ You said: '{text}'", Fore.GREEN)
                return text
                
            except sr.WaitTimeoutError:
                return None
            except Exception as e:
                err = YourAIUnexpectedError(cause=e, module="ears_listen")
                log_exception("EARS", err)
                return None
                
    except OSError as e:
        err = YourAISystemError(message="Kein Mikrofon gefunden oder Zugriff verweigert.", cause=e, module="ears_listen")
        log_exception("EARS", err)
        return None
    except AttributeError as e:
        err = YourAISystemError(message="PyAudio (Mikrofon-Treiber) fehlt oder ist fehlerhaft.", cause=e, module="ears_listen")
        log_exception("EARS", err)
        return None

if __name__ == "__main__":
    while True:
        listen()