(function (root, factory) {
    const api = factory();
    if (typeof module === "object" && module.exports) module.exports = api;
    root.EspnDraftExtractor = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
    "use strict";

    const POSITION = "(QB|RB|WR|TE|K|D\\/ST|DST|DEF)";
    const NAME = "([A-Z][A-Za-z.'’\\-]+(?:\\s+(?:[A-Z][A-Za-z.'’\\-]+|Jr\\.?|Sr\\.?|II|III|IV)){1,4})";
    const nameBeforePosition = new RegExp(NAME + "\\s+" + POSITION + "\\b");
    const positionBeforeName = new RegExp("\\b" + POSITION + "\\s+" + NAME);

    function normalizePosition(value) {
        const position = String(value || "").toUpperCase();
        return position === "DST" || position === "D/ST" ? "DEF" : position;
    }

    function cleanName(value) {
        return String(value || "")
            .replace(/^Pick\s+\d+\s*/i, "")
            .replace(/^\d+\.\d+\s*/, "")
            .replace(/^\d+[.)]\s*/, "")
            .replace(/\s+/g, " ")
            .trim();
    }

    function stripTrailingTeam(value) {
        return String(value || "").replace(/\s+(?!II$|III$|IV$)[A-Z]{2,3}$/, "");
    }

    function parsePickText(rawText) {
        const text = String(rawText || "").replace(/\s+/g, " ").trim();
        if (!text || text.length > 300) return null;

        let pickNumber = null;
        let round = null;
        let draftSlot = null;
        let match = text.match(/\bPick\s*#?\s*(\d{1,3})\b/i);
        if (match) pickNumber = Number(match[1]);

        match = text.match(/(?:^|\s)(\d{1,2})\.(\d{1,2})(?:\s|$)/);
        if (match) {
            round = Number(match[1]);
            draftSlot = Number(match[2]);
        }

        if (!pickNumber) {
            match = text.match(/^\s*(\d{1,3})[.)]\s+/);
            if (match) pickNumber = Number(match[1]);
        }

        const byName = text.match(nameBeforePosition);
        const byPosition = byName ? null : text.match(positionBeforeName);
        if (!byName && !byPosition) return null;

        const playerName = cleanName(byName ? byName[1] : stripTrailingTeam(byPosition[2]));
        const position = normalizePosition(byName ? byName[2] : byPosition[1]);
        if (!playerName || (!pickNumber && !round)) return null;

        return { pickNumber, round, draftSlot, playerName, position };
    }

    function scanDocument(doc) {
        const selectors = [
            "[data-testid*='pick']",
            "[data-testid*='draft'] [role='row']",
            "[class*='pick']",
            "[class*='draft'] [role='row']",
            "[aria-label*='pick' i]"
        ];
        const nodes = Array.from(doc.querySelectorAll(selectors.join(","))).slice(0, 2500);
        const results = [];
        const seen = new Set();

        nodes.forEach(node => {
            const parsed = parsePickText(node.innerText || node.textContent || node.getAttribute("aria-label"));
            if (!parsed) return;
            const key = [
                parsed.pickNumber || "",
                parsed.round || "",
                parsed.draftSlot || "",
                parsed.playerName,
                parsed.position
            ].join("|");
            if (seen.has(key)) return;
            seen.add(key);
            results.push(parsed);
        });

        return results.sort((a, b) =>
            (a.pickNumber || ((a.round || 999) * 100 + (a.draftSlot || 99))) -
            (b.pickNumber || ((b.round || 999) * 100 + (b.draftSlot || 99)))
        );
    }

    return { parsePickText, scanDocument, normalizePosition };
});
