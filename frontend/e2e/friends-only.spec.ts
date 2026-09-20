import { devices, expect, test, type BrowserContext, type Page } from "@playwright/test";

const adminPassword = process.env.E2E_ADMIN_PASSWORD;

async function signInAndHost(page: Page) {
  if (!adminPassword) {
    throw new Error("E2E_ADMIN_PASSWORD must match the test backend configuration");
  }
  await page.goto("/login");
  await page.getByLabel("Password").fill(adminPassword);
  await page.getByRole("button", { name: /^Sign in/ }).click();
  await expect(page.getByRole("button", { name: /Host Game/ })).toBeVisible();
  await page.getByRole("button", { name: /Host Game/ }).click();
  await expect(page.getByRole("heading", { name: "Friend invitations" })).toBeVisible();
  await expect(page.locator(".friend-invite")).toHaveCount(3);
}

async function invitationLinks(page: Page) {
  return page.evaluate(() => {
    const key = Object.keys(sessionStorage).find((item) => item.endsWith(":invitations"));
    if (!key) throw new Error("Invitation material was not stored for the host");
    const invitations = JSON.parse(sessionStorage.getItem(key) ?? "[]") as Array<{ secret?: string }>;
    return invitations.map((invitation) => {
      if (!invitation.secret) throw new Error("Invitation secret is missing");
      return `${location.origin}/invite#${invitation.secret}`;
    });
  });
}

async function enterFriend(page: Page, link: string) {
  await page.goto(link);
  await expect(page).toHaveURL(/\/invite#/);
  await page.getByRole("button", { name: /Enter Gravity Wars/ }).click();
  await expect(page.getByText("Your seat is reserved")).toBeVisible();
  await expect(page).toHaveURL(/\/lobby\/[^#]+$/);
}

test("uninvited visitors see the private gate", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Private game" })).toBeVisible();
  await expect(page.locator(".access-x")).toBeVisible();
  if (process.env.VISUAL_REVIEW) {
    await page.screenshot({
      path: `/tmp/gravitywars-${await page.evaluate(() => innerWidth < 600) ? "mobile" : "desktop"}-private.png`,
      fullPage: true,
    });
  }
  await page.goto("/lobby/not-an-invitation");
  await expect(page.getByRole("heading", { name: "Private game" })).toBeVisible();
});

test("admin invites three isolated friends, finishes a game, then replays with the same crew", async ({ browser, baseURL, isMobile }) => {
  const contexts: BrowserContext[] = [];
  const frames: string[][] = [[], [], [], []];
  const device = isMobile ? devices["Pixel 7"] : devices["Desktop Chrome"];
  try {
    const adminContext = await browser.newContext({ ...device, baseURL });
    contexts.push(adminContext);
    const admin = await adminContext.newPage();
    admin.on("websocket", (socket) => socket.on("framereceived", ({ payload }) => frames[0].push(String(payload))));
    await signInAndHost(admin);
    const links = await invitationLinks(admin);
    expect(new Set(links).size).toBe(3);

    const players = [admin];
    for (let index = 0; index < links.length; index += 1) {
      const context = await browser.newContext({ ...device, baseURL });
      contexts.push(context);
      const friend = await context.newPage();
      friend.on("websocket", (socket) => socket.on("framereceived", ({ payload }) => frames[index + 1].push(String(payload))));
      await enterFriend(friend, links[index]);
      players.push(friend);
    }

    await expect(admin.locator(".seat-count")).toContainText("4");
    if (process.env.VISUAL_REVIEW) {
      await admin.screenshot({
        path: `/tmp/gravitywars-${isMobile ? "mobile" : "desktop"}-lobby.png`,
        fullPage: true,
      });
    }
    await admin.getByRole("button", { name: "Start Game" }).click();
    for (const player of players) {
      await expect(player.getByRole("region", { name: "Your private joker hand" }).locator(".joker-card")).toHaveCount(2);
    }

    for (const received of frames) {
      const messages = received.flatMap((frame) => {
        try { return [JSON.parse(frame) as Record<string, unknown>]; }
        catch { return []; }
      });
      const states = messages.filter((message) => message.type === "state");
      expect(states.length).toBeGreaterThan(0);
      for (const state of states) expect(JSON.stringify(state)).not.toContain('"jokers"');
      const privateHands = messages.filter((message) => message.type === "hand") as Array<{ jokers: string[] }>;
      expect(privateHands).toHaveLength(1);
      expect(privateHands[0].jokers).toHaveLength(2);
    }
    if (process.env.VISUAL_REVIEW) {
      await admin.screenshot({
        path: `/tmp/gravitywars-${isMobile ? "mobile" : "desktop"}-game.png`,
        fullPage: true,
      });
    }

    const moves = [0, 6, 6, 6, 1, 5, 5, 5, 2, 4, 4, 4, 3];
    for (let turn = 0; turn < moves.length; turn += 1) {
      const player = players[turn % 4];
      await expect(player.getByText("Your turn", { exact: true })).toBeVisible();
      await player.getByRole("button", { name: `Drop piece in column ${moves[turn] + 1}` }).click();
    }
    await expect(admin.getByRole("heading", { name: "Victory!" })).toBeVisible();

    const originalUrls = players.map((player) => player.url());
    await admin.getByRole("button", { name: /Play Again/ }).click();
    await expect(admin.getByRole("heading", { name: "Victory!" })).not.toBeVisible();
    for (let index = 0; index < players.length; index += 1) {
      const player = players[index];
      await expect(player).toHaveURL(originalUrls[index]);
      await expect(player.getByRole("region", { name: "Your private joker hand" }).locator(".joker-card")).toHaveCount(2);
    }
    await expect(admin.getByText("Your turn", { exact: true })).toBeVisible();
    await admin.getByRole("button", { name: "Drop piece in column 1" }).click();
    await expect(players[1].getByText("Your turn", { exact: true })).toBeVisible();
  } finally {
    await Promise.all(contexts.map((context) => context.close()));
  }
});

test("a redeemed friend can refresh and explicit leave revokes the seat", async ({ browser, baseURL, isMobile }) => {
  const device = isMobile ? devices["Pixel 7"] : devices["Desktop Chrome"];
  const adminContext = await browser.newContext({ ...device, baseURL });
  const friendContext = await browser.newContext({ ...device, baseURL });
  try {
    const admin = await adminContext.newPage();
    await signInAndHost(admin);
    const [link] = await invitationLinks(admin);
    const friend = await friendContext.newPage();
    await enterFriend(friend, link);
    const lobbyUrl = friend.url();
    await friend.reload();
    await expect(friend.getByText("Your seat is reserved")).toBeVisible();
    await friend.getByRole("button", { name: "Leave Lobby" }).click();
    await expect(friend.getByRole("heading", { name: "Private game" })).toBeVisible();
    await friend.goto(lobbyUrl);
    await expect(friend.getByRole("heading", { name: "Private game" })).toBeVisible();
  } finally {
    await friendContext.close();
    await adminContext.close();
  }
});
