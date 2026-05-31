"""
Body Ears - Speech to Text
==========================
Handles recording audio from the system microphone and transcribing it to text using a local faster-whisper model.

Main Responsibilities:
- Initialize the Whisper model on CPU or CUDA.
- Record audio via speech_recognition and export to a temporary WAV file.
- Transcribe the temporary audio file to English text.

Side Effects:
- Accesses system audio input devices (microphone).
- Reads and writes transient files to TEMP_SPEECH_PATH.
"""

import os
import sys

import speech_recognition as sr
from faster_whisper import WhisperModel

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths  # noqa: F401

from display import log, log_exception, Fore
from exceptions import YourAIUnexpectedError, YourAISystemError
from body.audio_temp import TEMP_SPEECH_PATH, remove_temp_audio

from config import (
    WHISPER_MODEL_SIZE,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
    WHISPER_PHRASE_TIME_LIMIT,
    WHISPER_BEAM_SIZE,
    WHISPER_AMBIENT_NOISE_DURATION,
)

MODEL_SIZE = WHISPER_MODEL_SIZE
DEVICE = WHISPER_DEVICE
COMPUTE_TYPE = WHISPER_COMPUTE_TYPE

log("EARS", f"Loading Whisper Model '{MODEL_SIZE}' on {DEVICE}...", Fore.CYAN)
try:
    model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
    log("EARS", "Whisper ready (English Mode)!", Fore.GREEN)
except Exception as e:
    err = YourAISystemError(
        message="Whisper model could not be loaded, possibly out of memory",
        cause=e,
        module="ears_init",
    )
    log_exception("EARS", err)
    model = None


def listen():
    """
    Listens to microphone audio and transcribes it to English text.

    Adjusts for ambient noise prior to recording. Falls back to console input
    if the Whisper model failed to initialize.

    Returns:
        Optional[str]: The transcribed text, or None if silence was heard, a timeout 
                       occurred, or transcription failed.
    """
    if model is None:
        return input("Fallback (No Whisper) - Type here: ")

    recognizer = sr.Recognizer()

    try:
        with sr.Microphone() as source:
            log("EARS", "AltPersona/YourAI is listening... (Speak English!)", Fore.MAGENTA)
            recognizer.adjust_for_ambient_noise(source, duration=WHISPER_AMBIENT_NOISE_DURATION)

            try:
                audio = recognizer.listen(source, timeout=None, phrase_time_limit=WHISPER_PHRASE_TIME_LIMIT)
                log("EARS", "Thinking (Transcribing)...", Fore.YELLOW)

                with open(TEMP_SPEECH_PATH, "wb") as f:
                    f.write(audio.get_wav_data())

                segments, _ = model.transcribe(
                    TEMP_SPEECH_PATH,
                    beam_size=WHISPER_BEAM_SIZE,
                    language="en",
                )
                text = " ".join([segment.text for segment in segments]).strip()
                remove_temp_audio(TEMP_SPEECH_PATH, "EARS")

                if not text:
                    log("EARS", "Heard silence.", Fore.LIGHTBLACK_EX)
                    return None

                log("EARS", f"You said: '{text}'", Fore.GREEN)
                return text

            except sr.WaitTimeoutError:
                return None
            except Exception as e:
                err = YourAIUnexpectedError(cause=e, module="ears_listen")
                log_exception("EARS", err)
                return None

    except OSError as e:
        err = YourAISystemError(
            message="No microphone found or access denied",
            cause=e,
            module="ears_listen",
        )
        log_exception("EARS", err)
        return None
    except AttributeError as e:
        err = YourAISystemError(
            message="PyAudio microphone driver is missing or broken",
            cause=e,
            module="ears_listen",
        )
        log_exception("EARS", err)
        return None


if __name__ == "__main__":
    while True:
        listen()
