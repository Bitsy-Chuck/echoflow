#!/usr/bin/env python3
"""
EchoFlow runner — switch between STT engines.

Set STT_ENGINE below to "chirp" or "sarvam".
"""

STT_ENGINE = "chirp"  # "chirp" or "sarvam"

if __name__ == "__main__":
    if STT_ENGINE == "chirp":
        from main import main
    elif STT_ENGINE == "sarvam":
        from sarvam_main import main
    else:
        raise ValueError(f"Unknown STT_ENGINE: {STT_ENGINE!r}. Use 'chirp' or 'sarvam'.")
    main()
