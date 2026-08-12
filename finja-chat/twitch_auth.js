/* ========================================================================
 * Project: Finja - Twitch Interactivity Suite
 * Module: finja-chat / twitch_auth.js
 * Author: J. Apps (JohnV2002 / Sodakiller1)
 * Version: 2.4.1
 * Description: Twitch Device Code OAuth, validation, and token rotation.
 * New in v2.4.1:
 *   - Keeps OAuth access and refresh tokens in page memory only.
 *   - Removes clear-text OAuth data left by older browser sessions.
 * Copyright (c) 2026 J. Apps
 * Licensed under the MIT License.
 * ====================================================================== */

(function exposeTwitchAuth(root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.FinjaTwitchAuth = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function createTwitchAuthApi() {
  "use strict";

  const VERSION = "2.4.1";
  const LEGACY_TOKEN_KEYS = ["finja_twitch_auth_v1", "finja_bot_oauth"];
  const CLIENT_ID_KEY = "finja_twitch_client_id";
  const SCOPES = ["chat:read", "chat:edit"];
  const DEVICE_ENDPOINT = "https://id.twitch.tv/oauth2/device";
  const TOKEN_ENDPOINT = "https://id.twitch.tv/oauth2/token";
  const VALIDATE_ENDPOINT = "https://id.twitch.tv/oauth2/validate";
  const ERROR_CODES = Object.freeze({
    AUTH: "FINJA-401",
    DEVICE: "FINJA-404",
    REFRESH: "FINJA-405",
    RECONNECT: "FINJA-406",
  });

  class TwitchAuthError extends Error {
    constructor(code, message, cause) {
      super(`[${code}] ${message}`);
      this.name = "TwitchAuthError";
      this.code = code;
      this.cause = cause;
    }
  }

  const defaultSleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

  function normalizedClientId(value) {
    return String(value || "").trim();
  }

  function accessToken(value) {
    return String(value || "").trim().replace(/^oauth:/i, "");
  }

  async function responseJson(response) {
    try {
      return await response.json();
    } catch (cause) {
      throw new TwitchAuthError(ERROR_CODES.AUTH, "Twitch returned an unreadable OAuth response.", cause);
    }
  }

  class TwitchAuthManager {
    constructor(options = {}) {
      const runtime = typeof globalThis !== "undefined" ? globalThis : {};
      this.fetchImpl = options.fetchImpl || (runtime.fetch && runtime.fetch.bind(runtime));
      this.storage = options.storage || runtime.localStorage;
      this.session = null;
      this.now = options.now || (() => Date.now());
      this.sleep = options.sleep || defaultSleep;
      if (!this.fetchImpl || !this.storage) {
        throw new TwitchAuthError(ERROR_CODES.AUTH, "Twitch OAuth requires fetch and local storage.");
      }
      LEGACY_TOKEN_KEYS.forEach((key) => this.storage.removeItem(key));
    }

    getClientId() {
      return normalizedClientId(this.storage.getItem(CLIENT_ID_KEY));
    }

    setClientId(clientId) {
      const normalized = normalizedClientId(clientId);
      if (!normalized) throw new TwitchAuthError(ERROR_CODES.AUTH, "A Twitch Client ID is required.");
      this.storage.setItem(CLIENT_ID_KEY, normalized);
      return normalized;
    }

    loadSession() {
      return this.session;
    }

    saveSession(session) {
      const normalized = {
        accessToken: accessToken(session.accessToken),
        refreshToken: String(session.refreshToken || ""),
        clientId: normalizedClientId(session.clientId),
        expiresAt: Number(session.expiresAt || 0),
        login: String(session.login || ""),
        scopes: Array.isArray(session.scopes) ? session.scopes : SCOPES,
      };
      if (!normalized.accessToken || !normalized.refreshToken || !normalized.clientId) {
        throw new TwitchAuthError(ERROR_CODES.AUTH, "Twitch OAuth response did not contain a complete session.");
      }
      this.session = normalized;
      this.setClientId(normalized.clientId);
      return normalized;
    }

    clearSession() {
      this.session = null;
      LEGACY_TOKEN_KEYS.forEach((key) => this.storage.removeItem(key));
    }

    async postForm(url, parameters, failureCode) {
      let response;
      try {
        response = await this.fetchImpl(url, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: new URLSearchParams(parameters),
        });
      } catch (cause) {
        throw new TwitchAuthError(failureCode, "Twitch OAuth service is unreachable.", cause);
      }
      return { response, data: await responseJson(response) };
    }

    async startDeviceAuthorization(clientId) {
      const normalized = this.setClientId(clientId);
      const { response, data } = await this.postForm(
        DEVICE_ENDPOINT,
        { client_id: normalized, scopes: SCOPES.join(" ") },
        ERROR_CODES.DEVICE,
      );
      if (!response.ok || !data.device_code || !data.user_code || !data.verification_uri) {
        throw new TwitchAuthError(ERROR_CODES.DEVICE, data.message || "Twitch device authorization could not be started.");
      }
      return {
        clientId: normalized,
        deviceCode: data.device_code,
        userCode: data.user_code,
        verificationUri: data.verification_uri,
        expiresAt: this.now() + Number(data.expires_in || 600) * 1000,
        intervalMs: Math.max(1000, Number(data.interval || 5) * 1000),
        scopes: SCOPES,
      };
    }

    async pollDeviceAuthorization(request) {
      let intervalMs = request.intervalMs;
      while (this.now() < request.expiresAt) {
        await this.sleep(intervalMs);
        const { response, data } = await this.postForm(
          TOKEN_ENDPOINT,
          {
            client_id: request.clientId,
            scopes: request.scopes.join(" "),
            device_code: request.deviceCode,
            grant_type: "urn:ietf:params:oauth:grant-type:device_code",
          },
          ERROR_CODES.DEVICE,
        );
        if (response.ok) return this.sessionFromTokenResponse(data, request.clientId);
        const message = String(data.message || "").toLowerCase();
        if (message === "authorization_pending") continue;
        if (message === "slow_down") {
          intervalMs += 5000;
          continue;
        }
        throw new TwitchAuthError(ERROR_CODES.DEVICE, data.message || "Twitch device authorization failed.");
      }
      throw new TwitchAuthError(ERROR_CODES.DEVICE, "Twitch device authorization expired before confirmation.");
    }

    sessionFromTokenResponse(data, clientId, previous = {}) {
      return this.saveSession({
        accessToken: data.access_token,
        refreshToken: data.refresh_token,
        clientId,
        expiresAt: this.now() + Number(data.expires_in || 0) * 1000,
        login: previous.login || "",
        scopes: data.scope || previous.scopes || SCOPES,
      });
    }

    async refreshSession(session = this.loadSession()) {
      if (!session || !session.refreshToken) {
        throw new TwitchAuthError(ERROR_CODES.REFRESH, "No refreshable Twitch session is available.");
      }
      const { response, data } = await this.postForm(
        TOKEN_ENDPOINT,
        {
          grant_type: "refresh_token",
          refresh_token: session.refreshToken,
          client_id: session.clientId,
        },
        ERROR_CODES.REFRESH,
      );
      if (!response.ok) {
        throw new TwitchAuthError(ERROR_CODES.REFRESH, data.message || "Twitch rejected the refresh token.");
      }
      return this.sessionFromTokenResponse(data, session.clientId, session);
    }

    async validateSession(session = this.loadSession()) {
      if (!session) return { valid: false, reason: "missing" };
      let response;
      try {
        response = await this.fetchImpl(VALIDATE_ENDPOINT, {
          headers: { Authorization: `OAuth ${accessToken(session.accessToken)}` },
        });
      } catch (cause) {
        throw new TwitchAuthError(ERROR_CODES.AUTH, "Twitch token validation is unreachable.", cause);
      }
      if (response.status === 401) return { valid: false, reason: "unauthorized" };
      const data = await responseJson(response);
      if (!response.ok) throw new TwitchAuthError(ERROR_CODES.AUTH, data.message || "Twitch token validation failed.");
      const updated = this.saveSession({
        ...session,
        login: data.login || session.login,
        scopes: data.scopes || session.scopes,
        expiresAt: this.now() + Number(data.expires_in || 0) * 1000,
      });
      return { valid: true, session: updated, expiresIn: Number(data.expires_in || 0) };
    }

    async ensureSession(refreshMarginSeconds = 300) {
      const session = this.loadSession();
      if (!session) throw new TwitchAuthError(ERROR_CODES.AUTH, "Twitch authorization is required.");
      const validation = await this.validateSession(session);
      if (!validation.valid || validation.expiresIn <= refreshMarginSeconds) {
        return this.refreshSession(session);
      }
      return validation.session;
    }
  }

  return Object.freeze({
    VERSION,
    SCOPES,
    ERROR_CODES,
    TwitchAuthError,
    TwitchAuthManager,
  });
});
