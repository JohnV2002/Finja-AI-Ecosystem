"""
======================================================================
                     Web Crawler API – Token Gen
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module: finja-web-crawler
  Author: J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.0.0

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the Apache License 2.0

----------------------------------------------------------------------
  Description:
    A simple helper script to generate a secure, 64-character token.
    This generated token can be used in your .env file as the
    BEARER_TOKEN value to authenticate the Finja Web Crawler API.
======================================================================
"""

import secrets
import string

token = ''.join(secrets.choice(string.ascii_letters) for _ in range(64))
print(token)
