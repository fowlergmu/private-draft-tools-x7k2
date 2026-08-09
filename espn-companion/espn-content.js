"use strict";

const companionStatus = document.createElement("button");
companionStatus.type = "button";
companionStatus.textContent = "Draft Tool: watching ESPN";
companionStatus.title = "Private Draft Tools ESPN Companion is active";
Object.assign(companionStatus.style, {
    position: "fixed",
    right: "12px",
    bottom: "12px",
    zIndex: "2147483647",
    border: "1px solid #287c47",
    borderRadius: "999px",
    background: "#111a15",
    color: "#8ce6ae",
    padding: "7px 11px",
    font: "600 12px system-ui, sans-serif",
    boxShadow: "0 3px 12px rgba(0,0,0,.3)",
    cursor: "pointer"
});
document.documentElement.appendChild(companionStatus);

let lastSignature = "";
let scanTimer = null;

function sendStatus(message, connected) {
    chrome.runtime.sendMessage({
        type: "ESPN_COMPANION_STATUS",
        connected: connected !== false,
        message
    }).catch(() => null);
}

function scanEspnDraft() {
    const picks = EspnDraftExtractor.scanDocument(document);
    const signature = picks.map(p => [
        p.pickNumber || "",
        p.round || "",
        p.draftSlot || "",
        p.playerName,
        p.position
    ].join(":")).join("|");

    companionStatus.textContent = picks.length
        ? "Draft Tool: " + picks.length + " ESPN pick" + (picks.length === 1 ? "" : "s")
        : "Draft Tool: watching ESPN";
    sendStatus(picks.length ? "Connected · " + picks.length + " picks found" : "Connected · waiting for ESPN picks", true);

    if (signature === lastSignature) return;
    lastSignature = signature;
    chrome.runtime.sendMessage({
        type: "ESPN_DRAFT_SNAPSHOT",
        picks,
        pageUrl: location.href,
        capturedAt: new Date().toISOString()
    }).catch(() => null);
}

function scheduleScan() {
    clearTimeout(scanTimer);
    scanTimer = setTimeout(scanEspnDraft, 700);
}

companionStatus.addEventListener("click", scanEspnDraft);
chrome.runtime.onMessage.addListener(message => {
    if (message && message.type === "ESPN_SCAN_NOW") scanEspnDraft();
});

new MutationObserver(scheduleScan).observe(document.documentElement, {
    childList: true,
    subtree: true,
    characterData: true
});

sendStatus("Connected · waiting for ESPN picks", true);
scanEspnDraft();
