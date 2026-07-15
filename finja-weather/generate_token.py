"""
======================================================================
         Finja Weather API – Token Generator
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-weather / generate_token
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.0

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

  Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
  Website: https://jappshome.de
  Support: https://buymeacoffee.com/J.Apps

----------------------------------------------------------------------
 Description:
----------------------------------------------------------------------
  Generate a random bearer token for the Finja Weather API .env file.
======================================================================
"""

import secrets

if __name__ == "__main__":
    print(f"BEARER_TOKEN={secrets.token_urlsafe(48)}")
