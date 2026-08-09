(function () {
    "use strict";

    const PROJECTION_CACHE_KEY = "fantasyDraftEngine_projectionCache";
    const COMPARISON_KEY = "fantasyDraftEngine_comparisonPlayers";
    let cachedProjectionCsv = null;

    function playerForRosterEntry(entry) {
        const clean = String(entry || "").replace(/\s+\((QB|RB|WR|TE|DEF)\)$/, "");
        return activePlayers.find(p => p.name === clean) || null;
    }

    function formatSourceTime(kind) {
        const value = getLastSync(kind);
        return value ? formatSyncTime(value) : "not checked";
    }

    function renderSourceMeta() {
        const bar = document.getElementById("sourceMetaBar");
        if (!bar) return;
        const currentCount = activePlayers.filter(p => p.currentStatus).length;
        const projectionText = projectionSourceLabel || "Tier-modeled estimates";
        bar.innerHTML =
            "<span class='source-chip'><strong>Rankings:</strong> FantasyPros Full PPR · " +
            activePlayers.length + " players · checked " + escapeHtml(formatSourceTime("rankings")) + "</span>" +
            "<span class='source-chip'><strong>Injuries:</strong> NFL Daily News · " +
            currentCount + " current · checked " + escapeHtml(formatSourceTime("currentInjuries")) + "</span>" +
            "<span class='source-chip'><strong>Projections:</strong> " + escapeHtml(projectionText) + "</span>";
    }

    function injurySeverity(status) {
        return { IR: 7, PUP: 6, NFI: 6, Out: 5, Doubtful: 4, Questionable: 3, "Day-to-day": 2, Monitor: 1 }[status] || 0;
    }

    function renderCurrentInjuriesDashboard() {
        const container = document.getElementById("currentInjuriesDashboard");
        const summary = document.getElementById("injurySummary");
        if (!container) return;
        const injured = activePlayers
            .filter(p => p.currentStatus)
            .sort((a, b) => injurySeverity(b.currentStatus) - injurySeverity(a.currentStatus) || (a.adp || 9999) - (b.adp || 9999));
        if (summary) summary.textContent = injured.length + " player" + (injured.length === 1 ? "" : "s") + " being monitored";
        if (injured.length === 0) {
            container.innerHTML = "<p style='color:var(--text-muted);font-size:12px;'>No active fantasy-player injuries are in the current news snapshot.</p>";
            return;
        }
        container.innerHTML = injured.map(p => {
            const className = ["Out", "Doubtful"].includes(p.currentStatus) ? " out" : (["IR", "PUP", "NFI"].includes(p.currentStatus) ? " ir" : "");
            const source = p.currentInjurySource
                ? "<a href='" + escapeHtml(p.currentInjurySource) + "' target='_blank' rel='noopener'>Open source ↗</a>"
                : "";
            return "<article class='news-card" + className + "'>" +
                "<div style='display:flex;justify-content:space-between;gap:8px;align-items:flex-start;'>" +
                "<div><strong>" + escapeHtml(p.name) + "</strong> <span style='color:var(--text-muted);font-size:10px;'>" + escapeHtml(p.pos) + "</span></div>" +
                "<span class='status-badge badge-current-monitor'>" + escapeHtml(p.currentStatus) + "</span></div>" +
                "<div style='font-size:12px;margin-top:5px;'>" + escapeHtml(p.currentInjury || "Status update") + "</div>" +
                "<div style='font-size:10px;color:var(--text-muted);margin:4px 0;'>" +
                escapeHtml(p.currentInjuryNotes || "") + (p.currentInjuryUpdated ? " · Updated " + escapeHtml(p.currentInjuryUpdated) : "") +
                "</div>" + source + "</article>";
        }).join("");
    }

    function rosterPlayersForTeam(teamNum) {
        const roster = teamRosters[teamNum];
        if (!roster) return [];
        return Object.values(roster).flat().map(playerForRosterEntry).filter(Boolean);
    }

    function renderRosterWarnings() {
        const container = document.getElementById("rosterWarnings");
        if (!container) return;
        const cfg = readConfig();
        const roster = teamRosters[cfg.userPos];
        if (!roster) {
            container.innerHTML = "<div class='warning-item'>Set your draft slot to begin roster checks.</div>";
            return;
        }
        const warnings = [];
        [["QB", "QB"], ["RB", "RB"], ["WR", "WR"], ["TE", "TE"], ["DF", "DEF"]].forEach(([key, label]) => {
            const needed = cfg.req[label] || 0;
            const open = Math.max(0, needed - (roster[key] || []).length);
            if (open > 0) warnings.push("Need " + open + " more starting " + label + (open > 1 ? "s" : ""));
        });
        const players = rosterPlayersForTeam(cfg.userPos);
        const byes = {};
        const teams = {};
        players.forEach(p => {
            if (p.bye && p.bye !== "-") (byes[p.bye] = byes[p.bye] || []).push(p.name);
            if (p.nflTeam && p.nflTeam !== "FA") (teams[p.nflTeam] = teams[p.nflTeam] || []).push(p.name);
        });
        Object.entries(byes).filter(([, names]) => names.length >= 3).forEach(([week, names]) => {
            warnings.push("Bye Week " + week + " cluster: " + names.length + " players");
        });
        Object.entries(teams).filter(([, names]) => names.length >= 3).forEach(([team, names]) => {
            warnings.push(team + " concentration: " + names.length + " players");
        });
        const unavailable = players.filter(p => ["Out", "Doubtful", "IR", "PUP", "NFI"].includes(p.currentStatus));
        if (unavailable.length) warnings.push("Unavailable players rostered: " + unavailable.map(p => p.name).join(", "));
        if (warnings.length === 0) {
            container.innerHTML = "<div class='warning-item good'>No major roster-construction warnings.</div>";
            return;
        }
        container.innerHTML = warnings.slice(0, 6).map(w => "<div class='warning-item'>" + escapeHtml(w) + "</div>").join("");
    }

    window.toggleComparison = function (id) {
        const existing = comparisonPlayerIds.indexOf(id);
        if (existing !== -1) comparisonPlayerIds.splice(existing, 1);
        else if (comparisonPlayerIds.length < 3) comparisonPlayerIds.push(id);
        else {
            alert("Compare up to three players at a time. Remove one before adding another.");
            return;
        }
        try { localStorage.setItem(COMPARISON_KEY, JSON.stringify(comparisonPlayerIds)); } catch (e) {}
        recalculateEngine();
    };

    function renderPlayerComparison() {
        const container = document.getElementById("playerComparison");
        const count = document.getElementById("comparisonCount");
        if (!container) return;
        const players = comparisonPlayerIds.map(id => activePlayers.find(p => p.id === id)).filter(Boolean);
        comparisonPlayerIds = players.map(p => p.id);
        if (count) count.textContent = players.length ? players.length + " / 3 selected" : "";
        if (!players.length) {
            container.innerHTML = "<p style='color:var(--text-muted);font-size:12px;'>Use the ⇄ button beside any player to compare up to three options.</p>";
            return;
        }
        container.innerHTML = players.map(p =>
            "<div class='comparison-card'><div style='display:flex;justify-content:space-between;gap:6px;'>" +
            "<strong>" + escapeHtml(p.name) + "</strong><button class='favorite-toggle' onclick='toggleComparison(" + p.id + ")' aria-label='Remove " + escapeHtml(p.name) + " from comparison'>×</button></div>" +
            "<div style='color:var(--text-muted);margin-top:4px;'>" + escapeHtml(p.pos) + " · Tier " + p.tier + " · ADP " + Number(p.adp || 0).toFixed(0) + "</div>" +
            "<div style='display:grid;grid-template-columns:repeat(2,1fr);gap:3px;margin-top:5px;'>" +
            "<span>VOB <strong>" + Number(p.vob || 0).toFixed(1) + "</strong></span><span>Run <strong>" + Number(p.runRisk || 0) + "%</strong></span>" +
            "<span>Bye <strong>" + escapeHtml(p.bye || "—") + "</strong></span><span>Risk <strong>" + escapeHtml(p.currentStatus || p.injury || "Low") + "</strong></span>" +
            "</div><button class='btn' style='margin-top:7px;padding:4px;font-size:10px;' onclick='executePlayerDraft(" + p.id + ")'>Draft</button></div>"
        ).join("");
    }

    function populateQuickDraftPlayers() {
        const list = document.getElementById("quickDraftPlayers");
        if (!list) return;
        list.innerHTML = activePlayers.filter(p => !p.drafted).slice(0, 500)
            .map(p => "<option value='" + escapeHtml(p.name) + "'>" + escapeHtml(p.pos + " · Tier " + p.tier) + "</option>").join("");
    }

    window.quickDraftPlayer = function () {
        const input = document.getElementById("quickDraftInput");
        const query = input ? input.value.trim() : "";
        if (!query) return;
        const normalized = normalizeNameForMatch(query);
        const exact = activePlayers.find(p => !p.drafted && normalizeNameForMatch(p.name) === normalized);
        const partial = activePlayers.filter(p => !p.drafted && normalizeNameForMatch(p.name).includes(normalized));
        const player = exact || (partial.length === 1 ? partial[0] : null);
        if (!player) {
            alert(partial.length > 1 ? "More than one player matches. Type the full name." : "No undrafted player matches that name.");
            return;
        }
        if (executePlayerDraft(player.id) && input) input.value = "";
    };

    function draftReportData() {
        const cfg = readConfig();
        const picks = draftHistory.filter(h => h.team === cfg.userPos).map(h => h.playerObj);
        if (!picks.length) return null;
        const startersNeeded = cfg.req.QB + cfg.req.RB + cfg.req.WR + cfg.req.TE + cfg.req.Flex + cfg.req.DEF;
        const roster = teamRosters[cfg.userPos];
        const startersFilled = roster.QB.length + roster.RB.length + roster.WR.length + roster.TE.length + roster.FX.length + roster.DF.length;
        const values = picks.map(p => Number(p.draftPick || 0) - Number(p.adp || p.draftPick || 0));
        const averageValue = values.reduce((a, b) => a + b, 0) / values.length;
        const risky = picks.filter(p => ["High", "Yikes"].includes(p.injury) || ["Out", "Doubtful", "IR", "PUP", "NFI"].includes(p.currentStatus)).length;
        const fillRate = startersNeeded ? startersFilled / startersNeeded : 1;
        let score = 58 + Math.min(18, fillRate * 18) + Math.max(-12, Math.min(14, averageValue / 2)) - risky * 2;
        if (isDraftComplete(cfg) && startersFilled >= startersNeeded) score += 8;
        score = Math.max(0, Math.min(100, Math.round(score)));
        const letter = score >= 93 ? "A" : score >= 85 ? "B+" : score >= 78 ? "B" : score >= 70 ? "C+" : score >= 62 ? "C" : score >= 55 ? "D" : "F";
        const best = picks.slice().sort((a, b) => ((b.draftPick || 0) - (b.adp || 0)) - ((a.draftPick || 0) - (a.adp || 0)))[0];
        const reach = picks.slice().sort((a, b) => ((a.draftPick || 0) - (a.adp || 0)) - ((b.draftPick || 0) - (b.adp || 0)))[0];
        return { cfg, picks, score, letter, averageValue, risky, fillRate, best, reach };
    }

    function recapText() {
        const report = draftReportData();
        if (!report) return "No picks have been made yet.";
        return [
            "Fantasy Draft Report — Grade " + report.letter + " (" + report.score + "/100)",
            "Picks: " + report.picks.length,
            "Average value vs ADP: " + (report.averageValue >= 0 ? "+" : "") + report.averageValue.toFixed(1),
            "Best value: " + (report.best ? report.best.name : "—"),
            "Biggest reach: " + (report.reach ? report.reach.name : "—"),
            "High-risk selections: " + report.risky,
            "",
            report.picks.map(p => "Pick " + p.draftPick + ": " + p.name + " (" + p.pos + ", Tier " + p.tier + ")").join("\n")
        ].join("\n");
    }

    function renderDraftReport() {
        const container = document.getElementById("draftReportContent");
        const status = document.getElementById("draftReportStatus");
        if (!container) return;
        const report = draftReportData();
        if (!report) {
            if (status) status.textContent = "Appears after your first pick";
            container.innerHTML = "<p style='font-size:12px;color:var(--text-muted);'>Your live grade, roster strengths, values, reaches, and exportable recap will appear here.</p>";
            return;
        }
        const complete = isDraftComplete(report.cfg);
        if (status) status.textContent = complete ? "Final" : "Live draft grade";
        const strengths = [];
        if (report.averageValue >= 3) strengths.push("Strong value discipline");
        if (report.fillRate >= 1) strengths.push("Starting lineup filled");
        if (report.risky === 0) strengths.push("Low injury exposure");
        if (!strengths.length) strengths.push("Draft still developing");
        container.innerHTML =
            "<div class='report-grid'><div class='draft-grade'><strong>" + report.letter + "</strong><span>" + report.score + "/100</span></div>" +
            "<div><div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:6px;font-size:12px;'>" +
            "<span><strong>Best value:</strong> " + escapeHtml(report.best ? report.best.name : "—") + "</span>" +
            "<span><strong>Biggest reach:</strong> " + escapeHtml(report.reach ? report.reach.name : "—") + "</span>" +
            "<span><strong>Avg. value:</strong> " + (report.averageValue >= 0 ? "+" : "") + report.averageValue.toFixed(1) + "</span>" +
            "<span><strong>Risk flags:</strong> " + report.risky + "</span></div>" +
            "<p style='font-size:11px;color:var(--text-muted);margin-top:8px;'>" + escapeHtml(strengths.join(" · ")) + "</p>" +
            "<div style='display:flex;gap:6px;margin-top:8px;flex-wrap:wrap;'><button class='btn btn-secondary' style='width:auto;font-size:11px;' onclick='copyDraftRecap()'>Copy Recap</button>" +
            "<button class='btn btn-secondary' style='width:auto;font-size:11px;' onclick='downloadDraftRecap()'>Download Recap</button></div></div></div>";
    }

    window.copyDraftRecap = async function () {
        try {
            await navigator.clipboard.writeText(recapText());
            alert("Draft recap copied.");
        } catch (e) {
            alert("Clipboard access was unavailable. Use Download Recap instead.");
        }
    };

    window.downloadDraftRecap = function () {
        const blob = new Blob([recapText()], { type: "text/plain" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "fantasy-draft-recap.txt";
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    };

    window.toggleCompactMode = function () {
        const enabled = !document.body.classList.contains("compact-mode");
        document.body.classList.toggle("compact-mode", enabled);
        const button = document.getElementById("compactModeToggle");
        if (button) {
            button.setAttribute("aria-pressed", String(enabled));
            button.textContent = enabled ? "▣ Full Dashboard" : "⚡ Draft Focus";
        }
        try { localStorage.setItem(COMPACT_MODE_KEY, enabled ? "1" : "0"); } catch (e) {}
    };

    function restoreCompactMode() {
        let enabled = false;
        try { enabled = localStorage.getItem(COMPACT_MODE_KEY) === "1"; } catch (e) {}
        if (enabled) {
            document.body.classList.add("compact-mode");
            const button = document.getElementById("compactModeToggle");
            if (button) {
                button.setAttribute("aria-pressed", "true");
                button.textContent = "▣ Full Dashboard";
            }
        }
    }

    window.handleProjectionFile = function (file) {
        if (!file) return;
        const reader = new FileReader();
        reader.onload = e => mergeProjectionCsv(e.target.result);
        reader.onerror = () => alert("Could not read the projection file.");
        reader.readAsText(file);
    };

    window.mergeProjectionCsv = function (text, options) {
        options = options || {};
        if (!text || !text.trim()) {
            if (!options.silent) alert("Paste or select a projections CSV first.");
            return false;
        }
        const lines = text.split(/\r?\n/).filter(Boolean);
        const headers = parseCsvLine(lines[0]).map(h => h.toLowerCase().trim().replace(/\s+/g, "_"));
        const nameIdx = headers.indexOf("name") !== -1 ? headers.indexOf("name") : headers.indexOf("player");
        const projectionIdx = headers.findIndex(h => ["projected_points", "projection", "points", "fantasy_points"].includes(h));
        const floorIdx = headers.indexOf("floor");
        const ceilingIdx = headers.indexOf("ceiling");
        const sourceIdx = headers.indexOf("source");
        if (nameIdx === -1 || projectionIdx === -1) {
            if (!options.silent) alert("Projection CSV needs name and projected_points columns.");
            return false;
        }
        const matcher = buildPoolMatcher();
        let matched = 0;
        let source = "";
        for (let i = 1; i < lines.length; i++) {
            const cells = parseCsvLine(lines[i]);
            const projected = parseFloat(cells[projectionIdx]);
            if (!cells[nameIdx] || !Number.isFinite(projected)) continue;
            const result = matcher.find(cells[nameIdx]);
            if (!result.player) continue;
            result.player.projectedPoints = projected;
            result.player.projectionType = "imported";
            result.player.floor = floorIdx !== -1 && Number.isFinite(parseFloat(cells[floorIdx])) ? parseFloat(cells[floorIdx]) : projected * 0.9;
            result.player.ceiling = ceilingIdx !== -1 && Number.isFinite(parseFloat(cells[ceilingIdx])) ? parseFloat(cells[ceilingIdx]) : projected * 1.1;
            if (!source && sourceIdx !== -1) source = (cells[sourceIdx] || "").trim();
            matched++;
        }
        if (!matched) {
            if (!options.silent) alert("No projection names matched the current player pool.");
            return false;
        }
        projectionSourceLabel = source || "Imported projections";
        if (!options.skipCache) {
            cachedProjectionCsv = text;
            try {
                localStorage.setItem(PROJECTION_CACHE_KEY, text);
                localStorage.setItem(PROJECTION_SOURCE_KEY, projectionSourceLabel);
            } catch (e) {}
            touchLastSync(["projections"]);
        }
        recalculateEngine();
        saveState();
        if (!options.silent) alert("Merged projections for " + matched + " players.");
        return true;
    };

    function renderProjectionStatus() {
        const status = document.getElementById("projectionStatus");
        if (!status) return;
        const imported = activePlayers.filter(p => p.projectionType === "imported").length;
        const columnLabel = imported === 0 ? "modeled*" : (imported === activePlayers.length ? "imported*" : "mixed*");
        document.querySelectorAll(".modeled-label").forEach(el => { el.textContent = columnLabel; });
        status.textContent = imported
            ? projectionSourceLabel + " · " + imported + " players matched"
            : "Using tier-modeled estimates.";
    }

    function sleeperDraftIdFromInput() {
        const input = document.getElementById("sleeperDraftId");
        const match = String(input ? input.value : "").match(/(\d{8,})/);
        return match ? match[1] : "";
    }

    function setSleeperStatus(message, connected) {
        const status = document.getElementById("sleeperSettingsStatus");
        const badge = document.getElementById("sleeperLiveBadge");
        if (status) status.textContent = message;
        if (badge) badge.innerHTML = "<strong>Sleeper:</strong> " + escapeHtml(connected ? message : "not connected");
    }

    async function fetchSleeperJson(path) {
        const response = await fetch("https://api.sleeper.app/v1" + path, { cache: "no-store" });
        if (!response.ok) throw new Error("Sleeper returned HTTP " + response.status);
        return response.json();
    }

    function matchSleeperPlayer(pick) {
        const metadata = pick.metadata || {};
        const name = [metadata.first_name, metadata.last_name].filter(Boolean).join(" ").trim();
        const normalized = normalizeNameForMatch(name);
        let player = activePlayers.find(p => normalizeNameForMatch(p.name) === normalized);
        const pos = String(metadata.position || "").toUpperCase();
        if (!player && (pos === "DEF" || pos === "DST") && metadata.team) {
            player = activePlayers.find(p => p.pos === "DEF" && p.nflTeam === metadata.team);
        }
        return player || null;
    }

    function applySleeperPicks(picks) {
        const sorted = (Array.isArray(picks) ? picks : []).slice().sort((a, b) => Number(a.pick_no) - Number(b.pick_no));
        const signature = sorted.map(p => p.pick_no + ":" + p.player_id).join("|");
        if (sleeperDraftInfo && sleeperDraftInfo.lastSignature === signature) return { applied: 0, unmatched: 0, unchanged: true };
        resetDraftState();
        const cfg = readConfig();
        let applied = 0;
        let unmatched = 0;
        sorted.forEach(pick => {
            const player = matchSleeperPlayer(pick);
            const team = Math.max(1, Math.min(cfg.size, Number(pick.draft_slot) || getActivePickingTeam(Number(pick.pick_no), cfg.size)));
            if (!player || player.drafted || !teamRosters[team]) {
                unmatched++;
                return;
            }
            const placedSlot = findPlacementSlot(team, player, cfg);
            if (!placedSlot) {
                unmatched++;
                return;
            }
            teamRosters[team][placedSlot].push((placedSlot === "FX" || placedSlot === "BN") ? player.name + " (" + player.pos + ")" : player.name);
            player.drafted = true;
            player.draftPick = Number(pick.pick_no);
            player.draftedByTeam = team;
            player.placedSlot = placedSlot;
            draftHistory.push({ pick: Number(pick.pick_no), playerObj: player, team, slot: placedSlot, source: "sleeper" });
            applied++;
        });
        currentPick = sorted.length ? Math.max.apply(null, sorted.map(p => Number(p.pick_no) || 0)) + 1 : 1;
        if (sleeperDraftInfo) sleeperDraftInfo.lastSignature = signature;
        recalculateEngine();
        saveState();
        return { applied, unmatched, unchanged: false };
    }

    async function syncSleeperDraft(options) {
        options = options || {};
        const id = sleeperDraftIdFromInput();
        if (!id) {
            if (!options.silent) alert("Enter a valid Sleeper draft ID or draft URL.");
            return;
        }
        try {
            setSleeperStatus("syncing…", true);
            const results = await Promise.all([
                fetchSleeperJson("/draft/" + id),
                fetchSleeperJson("/draft/" + id + "/picks")
            ]);
            sleeperDraftInfo = Object.assign({}, results[0], { lastSignature: sleeperDraftInfo && sleeperDraftInfo.lastSignature });
            const draft = results[0];
            const picks = results[1];
            if (draft.settings && draft.settings.teams) {
                const leagueInput = document.getElementById("leagueSize");
                if (leagueInput && !draftHistory.length) leagueInput.value = draft.settings.teams;
            }
            const result = applySleeperPicks(picks);
            const label = (draft.metadata && draft.metadata.name ? draft.metadata.name + " · " : "") +
                picks.length + " picks" + (result.unmatched ? " · " + result.unmatched + " unmatched" : "");
            setSleeperStatus(label, true);
            try {
                localStorage.setItem(SLEEPER_CONFIG_KEY, JSON.stringify({ draftId: id, connected: true, autoSync: document.getElementById("sleeperAutoSync").checked }));
            } catch (e) {}
            configureSleeperPolling();
        } catch (e) {
            setSleeperStatus("Sync failed: " + e.message, false);
            if (!options.silent) alert("Sleeper sync failed: " + e.message);
        }
    }

    window.connectSleeperDraft = function () {
        if (draftHistory.length && !sleeperDraftInfo && !confirm("Connect to Sleeper and replace the current manual/mock draft with Sleeper picks?")) return;
        syncSleeperDraft();
    };

    window.disconnectSleeperDraft = function () {
        if (sleeperPollTimer) clearInterval(sleeperPollTimer);
        sleeperPollTimer = null;
        sleeperDraftInfo = null;
        try { localStorage.removeItem(SLEEPER_CONFIG_KEY); } catch (e) {}
        setSleeperStatus("Not connected.", false);
    };

    window.configureSleeperPolling = function () {
        if (sleeperPollTimer) clearInterval(sleeperPollTimer);
        sleeperPollTimer = null;
        const auto = document.getElementById("sleeperAutoSync");
        if (sleeperDraftInfo && auto && auto.checked) {
            sleeperPollTimer = setInterval(() => syncSleeperDraft({ silent: true }), 15000);
        }
    };

    function restoreSleeperConfig() {
        try {
            const raw = localStorage.getItem(SLEEPER_CONFIG_KEY);
            if (!raw) return;
            const config = JSON.parse(raw);
            const input = document.getElementById("sleeperDraftId");
            const auto = document.getElementById("sleeperAutoSync");
            if (input) input.value = config.draftId || "";
            if (auto) auto.checked = config.autoSync !== false;
            if (config.connected && config.draftId) syncSleeperDraft({ silent: true });
        } catch (e) {}
    }

    function renderAllNewFeatures() {
        renderSourceMeta();
        renderCurrentInjuriesDashboard();
        renderRosterWarnings();
        renderPlayerComparison();
        populateQuickDraftPlayers();
        renderDraftReport();
        renderProjectionStatus();
    }

    const originalRecalculateEngine = recalculateEngine;
    recalculateEngine = function () {
        originalRecalculateEngine();
        renderAllNewFeatures();
    };

    const originalParseCsvText = parseCsvText;
    parseCsvText = function (text, options) {
        const ok = originalParseCsvText(text, options);
        if (ok && cachedProjectionCsv) mergeProjectionCsv(cachedProjectionCsv, { silent: true, skipCache: true });
        return ok;
    };

    function initializeDraftDayFeatures() {
        restoreCompactMode();
        try {
            cachedProjectionCsv = localStorage.getItem(PROJECTION_CACHE_KEY);
            projectionSourceLabel = localStorage.getItem(PROJECTION_SOURCE_KEY) || projectionSourceLabel;
            const savedComparison = JSON.parse(localStorage.getItem(COMPARISON_KEY) || "[]");
            comparisonPlayerIds = Array.isArray(savedComparison) ? savedComparison.slice(0, 3) : [];
        } catch (e) {}
        renderAllNewFeatures();
        restoreSleeperConfig();
    }

    const originalOnload = window.onload;
    window.onload = function (event) {
        if (originalOnload) originalOnload.call(window, event);
        initializeDraftDayFeatures();
    };
})();
