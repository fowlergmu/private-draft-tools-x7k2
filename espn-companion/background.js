"use strict";

const TOOL_URLS = [
    "https://fowlergmu.github.io/private-draft-tools-x7k2/*",
    "http://localhost/*",
    "http://127.0.0.1/*"
];

async function sendToToolTabs(message) {
    const tabs = await chrome.tabs.query({ url: TOOL_URLS });
    await Promise.all(tabs.map(tab => chrome.tabs.sendMessage(tab.id, message).catch(() => null)));
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (!message || !message.type) return;

    if (message.type === "ESPN_DRAFT_SNAPSHOT" || message.type === "ESPN_COMPANION_STATUS") {
        sendToToolTabs(message);
        return;
    }

    if (message.type === "DRAFT_TOOL_ESPN_PING") {
        chrome.tabs.query({ url: "https://fantasy.espn.com/*" }).then(async tabs => {
            if (!tabs.length) {
                await sendToToolTabs({
                    type: "ESPN_COMPANION_STATUS",
                    connected: false,
                    message: "Companion is installed, but no ESPN draft room is open."
                });
                sendResponse({ connected: false });
                return;
            }
            await Promise.all(tabs.map(tab => chrome.tabs.sendMessage(tab.id, { type: "ESPN_SCAN_NOW" }).catch(() => null)));
            sendResponse({ connected: true });
        });
        return true;
    }
});
