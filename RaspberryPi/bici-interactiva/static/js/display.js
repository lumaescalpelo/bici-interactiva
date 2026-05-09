const body = document.body;

const video = document.getElementById("mainVideo");

// GAME UI
const gameName = document.getElementById("gameName");
const gameSpeed = document.getElementById("gameSpeed");
const gameScore = document.getElementById("gameScore");
const gameRankingList = document.getElementById("gameRankingList");
const gameRankPosition = document.getElementById("gameRankPosition");

// RESULT UI
const resultName = document.getElementById("resultName");
const resultRank = document.getElementById("resultRank");
const resultRankingList = document.getElementById("resultRankingList");

const IDLE_VIDEO = "/static/videos/idle.mp4";
const GAME_VIDEO = "/static/videos/game.mp4";

let currentMode = "idle";


function formatScore(value) {
  return String(Number(value || 0)).padStart(4, "0");
}


function playIdle() {
  currentMode = "idle";

  body.classList.remove("game-mode", "result-mode");
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

  body.classList.remove("idle-mode", "result-mode");
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
}


function playResult() {
  currentMode = "result";

  body.classList.remove("idle-mode", "game-mode");
  body.classList.add("result-mode");

  // ocultamos video para que se vea la imagen de fondo del result overlay
  video.pause();
  video.style.display = "none";
}


function renderGameRanking(ranking, currentRank) {
  gameRankingList.innerHTML = "";

  if (!Array.isArray(ranking) || ranking.length === 0) {
    const item = document.createElement("li");
    item.textContent = "Sin registros";
    gameRankingList.appendChild(item);

    gameRankPosition.textContent = "--";
    return;
  }

  ranking.forEach((entry) => {
    const item = document.createElement("li");

    const rank = document.createElement("span");
    rank.className = "ranking-rank";
    rank.textContent = `${entry.rank}.`;

    const name = document.createElement("span");
    name.className = "ranking-name";
    name.textContent = entry.participant_name || "PARTICIPANTE";

    const points = document.createElement("span");
    points.className = "ranking-score";
    points.textContent = formatScore(entry.score);

    item.appendChild(rank);
    item.appendChild(name);
    item.appendChild(points);

    if (entry.is_current) {
      item.classList.add("current-player");
    }

    gameRankingList.appendChild(item);
  });

  if (currentRank !== null && currentRank !== undefined) {
    gameRankPosition.textContent = `#${currentRank}`;
  } else {
    gameRankPosition.textContent = "--";
  }
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

    // Datos de game
    gameName.textContent = data.participant_name || "PARTICIPANTE";
    gameSpeed.textContent = `${Number(data.speed || 0).toFixed(1)} km/h`;
    gameScore.textContent = `${formatScore(data.score || 0)} pts`;
    renderGameRanking(data.ranking || [], data.current_rank);

    // Datos de result
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