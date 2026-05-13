const body = document.body;

const video = document.getElementById("mainVideo");

// GAME UI
const gameName = document.getElementById("gameName");
const gameScore = document.getElementById("gameScore");
const gameRankPosition = document.getElementById("gameRankPosition");
const gameNearbyRankingList = document.getElementById("gameNearbyRankingList");

// RESULT UI
const resultName = document.getElementById("resultName");
const resultRank = document.getElementById("resultRank");
const resultRankingList = document.getElementById("resultRankingList");

const IDLE_VIDEO = "/static/videos/idle.mp4";
const GAME_VIDEO = "/static/videos/game.mp4";

// Debe coincidir con la espera del ESP32
const GAME_UI_DELAY_MS = 7000;

let currentMode = "idle";
let gameUiTimer = null;


function formatScore(value) {
  return String(Number(value || 0)).padStart(4, "0");
}


function hideGameUiTemporarily() {
  body.classList.remove("game-ui-visible");

  if (gameUiTimer) {
    clearTimeout(gameUiTimer);
  }

  gameUiTimer = setTimeout(() => {
    if (currentMode === "game") {
      body.classList.add("game-ui-visible");
    }
  }, GAME_UI_DELAY_MS);
}


function playIdle() {
  currentMode = "idle";

  if (gameUiTimer) {
    clearTimeout(gameUiTimer);
    gameUiTimer = null;
  }

  body.classList.remove("game-mode", "result-mode", "game-ui-visible");
  body.classList.add("idle-mode");

  video.style.display = "block";
  video.loop = true;

  if (!video.src.endsWith(IDLE_VIDEO)) {
    video.src = IDLE_VIDEO;
  }

  video.play().catch((error) => {
    console.error("No se pudo reproducir idle:", error);
  });
}


function playGame() {
  currentMode = "game";

  body.classList.remove("idle-mode", "result-mode", "game-ui-visible");
  body.classList.add("game-mode");

  video.style.display = "block";
  video.loop = false;

  if (!video.src.endsWith(GAME_VIDEO)) {
    video.src = GAME_VIDEO;
  }

  video.currentTime = 0;

  video.play().catch((error) => {
    console.error("No se pudo reproducir game:", error);
  });

  hideGameUiTemporarily();
}


function playResult() {
  currentMode = "result";

  if (gameUiTimer) {
    clearTimeout(gameUiTimer);
    gameUiTimer = null;
  }

  body.classList.remove("idle-mode", "game-mode", "game-ui-visible");
  body.classList.add("result-mode");

  video.pause();
  video.style.display = "none";
}


function renderNearbyRanking(ranking) {
  gameNearbyRankingList.innerHTML = "";

  if (!Array.isArray(ranking) || ranking.length === 0) {
    const item = document.createElement("li");
    item.textContent = "Sin ranking";
    gameNearbyRankingList.appendChild(item);
    return;
  }

  ranking.forEach((entry) => {
    const item = document.createElement("li");

    const rank = document.createElement("span");
    rank.className = "nearby-rank";
    rank.textContent = `${entry.rank}.`;

    const name = document.createElement("span");
    name.className = "nearby-name";
    name.textContent = entry.participant_name || "PARTICIPANTE";

    const points = document.createElement("span");
    points.className = "nearby-score";
    points.textContent = formatScore(entry.score);

    item.appendChild(rank);
    item.appendChild(name);
    item.appendChild(points);

    if (entry.is_current) {
      item.classList.add("current-player");
    }

    gameNearbyRankingList.appendChild(item);
  });
}


function renderResultPanel(panel) {
  resultRankingList.innerHTML = "";

  if (!panel) {
    resultName.textContent = "PARTICIPANTE";
    resultRank.textContent = "--";
    return;
  }

  resultName.textContent = panel.participant_name || "PARTICIPANTE";
  resultRank.textContent = panel.rank ? `#${panel.rank}` : "--";

  const entries = panel.entries || [];

  entries.forEach((entry) => {
    const item = document.createElement("li");

    const rank = document.createElement("span");
    rank.className = "result-ranking-rank";
    rank.textContent = `${entry.rank}.`;

    const name = document.createElement("span");
    name.className = "result-ranking-name";
    name.textContent = entry.participant_name || "PARTICIPANTE";

    const points = document.createElement("span");
    points.className = "result-ranking-score";
    points.textContent = `${formatScore(entry.score)} pts`;

    item.appendChild(rank);
    item.appendChild(name);
    item.appendChild(points);

    if (entry.is_current) {
      item.classList.add("current-player");
    }

    resultRankingList.appendChild(item);
  });
}


async function updateStateFromServer() {
  try {
    const response = await fetch("/api/state", {
      cache: "no-store"
    });

    const data = await response.json();

    // GAME DATA
    gameName.textContent = data.participant_name || "PARTICIPANTE";
    gameScore.textContent = `${formatScore(data.score || 0)} pts`;

    const rank = data.nearby_current_rank || data.current_rank;
    gameRankPosition.textContent = rank ? `#${rank}` : "--";

    renderNearbyRanking(data.nearby_ranking || []);

    // RESULT DATA
    renderResultPanel(data.last_result_panel);

    const serverMode = data.screen_mode || "idle";

    if (serverMode === "game" && currentMode !== "game") {
      playGame();
    } else if (serverMode === "result" && currentMode !== "result") {
      playResult();
    } else if (serverMode === "idle" && currentMode !== "idle") {
      playIdle();
    }

  } catch (error) {
    console.error("No se pudo leer /api/state", error);
  }
}


setInterval(updateStateFromServer, 100);

playIdle();
updateStateFromServer();