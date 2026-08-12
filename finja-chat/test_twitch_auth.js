/* ========================================================================
 * Project: Finja - Twitch Interactivity Suite
 * Module: finja-chat / test_twitch_auth.js
 * Author: J. Apps (JohnV2002 / Sodakiller1)
 * Version: 2.4.0
 * Description: Unit tests for Twitch Device Code OAuth and token rotation.
 * New in v2.4.0:
 *   - Covers device authorization, validation, and refresh-token rotation.
 * Copyright (c) 2026 J. Apps
 * Licensed under the MIT License.
 * ====================================================================== */

"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { ERROR_CODES, TwitchAuthManager } = require("./twitch_auth.js");

function memoryStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  };
}

function jsonResponse(status, data) {
  return { ok: status >= 200 && status < 300, status, json: async () => data };
}

const fixtureToken = (label) => `test-${label}`;

test("device authorization stores a refreshable session", async () => {
  let clock = 1_000;
  const replies = [
    jsonResponse(200, {
      device_code: "device-code",
      user_code: "ABCD1234",
      verification_uri: "https://www.twitch.tv/activate",
      expires_in: 600,
      interval: 1,
    }),
    jsonResponse(400, { message: "authorization_pending" }),
    jsonResponse(200, {
      access_token: fixtureToken("access-one"),
      refresh_token: fixtureToken("refresh-one"),
      expires_in: 14400,
      scope: ["chat:read", "chat:edit"],
    }),
  ];
  const manager = new TwitchAuthManager({
    fetchImpl: async () => replies.shift(),
    storage: memoryStorage(),
    now: () => clock,
    sleep: async (milliseconds) => { clock += milliseconds; },
  });

  const request = await manager.startDeviceAuthorization("public-client-id");
  const session = await manager.pollDeviceAuthorization(request);

  assert.equal(session.accessToken, fixtureToken("access-one"));
  assert.equal(session.refreshToken, fixtureToken("refresh-one"));
  assert.equal(manager.loadSession().clientId, "public-client-id");
});

test("refresh replaces both one-time tokens", async () => {
  const storage = memoryStorage();
  const manager = new TwitchAuthManager({
    fetchImpl: async () => jsonResponse(200, {
      access_token: fixtureToken("access-two"),
      refresh_token: fixtureToken("refresh-two"),
      expires_in: 14400,
      scope: ["chat:read", "chat:edit"],
    }),
    storage,
    now: () => 10_000,
  });
  manager.saveSession({
    accessToken: fixtureToken("access-one"),
    refreshToken: fixtureToken("refresh-one"),
    clientId: "public-client-id",
    expiresAt: 20_000,
    scopes: ["chat:read", "chat:edit"],
  });

  const refreshed = await manager.refreshSession();

  assert.equal(refreshed.accessToken, fixtureToken("access-two"));
  assert.equal(refreshed.refreshToken, fixtureToken("refresh-two"));
  assert.equal(manager.loadSession().refreshToken, fixtureToken("refresh-two"));
});

test("invalid access token is refreshed during session recovery", async () => {
  const storage = memoryStorage();
  const replies = [
    jsonResponse(401, { status: 401, message: "invalid access token" }),
    jsonResponse(200, {
      access_token: fixtureToken("recovered-access"),
      refresh_token: fixtureToken("recovered-refresh"),
      expires_in: 14400,
      scope: ["chat:read", "chat:edit"],
    }),
  ];
  const manager = new TwitchAuthManager({
    fetchImpl: async () => replies.shift(),
    storage,
    now: () => 20_000,
  });
  manager.saveSession({
    accessToken: fixtureToken("expired-access"),
    refreshToken: fixtureToken("valid-refresh"),
    clientId: "public-client-id",
    expiresAt: 10_000,
    scopes: ["chat:read", "chat:edit"],
  });

  const recovered = await manager.ensureSession();

  assert.equal(recovered.accessToken, fixtureToken("recovered-access"));
});

test("failed refresh uses the dedicated FINJA error code", async () => {
  const manager = new TwitchAuthManager({
    fetchImpl: async () => jsonResponse(400, { message: "Invalid refresh token" }),
    storage: memoryStorage(),
  });
  manager.saveSession({
    accessToken: fixtureToken("expired-access"),
    refreshToken: fixtureToken("expired-refresh"),
    clientId: "public-client-id",
    expiresAt: 0,
    scopes: ["chat:read", "chat:edit"],
  });

  await assert.rejects(() => manager.refreshSession(), (error) => error.code === ERROR_CODES.REFRESH);
});
