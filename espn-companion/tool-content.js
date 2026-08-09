"use strict";

window.addEventListener("message", event => {
    if (event.source !== window) return;
    const message = event.data || {};
    if (message.source !== "fantasy-draft-tool" || message.type !== "ESPN_COMPANION_PING") return;
    chrome.runtime.sendMessage({ type: "DRAFT_TOOL_ESPN_PING" }).catch(() => null);
});

chrome.runtime.onMessage.addListener(message => {
    if (!message || !message.type) return;
    if (message.type !== "ESPN_COMPANION_STATUS" && message.type !== "ESPN_DRAFT_SNAPSHOT") return;
    window.postMessage(Object.assign({ source: "espn-draft-companion" }, message), window.location.origin);
});

chrome.runtime.sendMessage({ type: "DRAFT_TOOL_ESPN_PING" }).catch(() => null);
