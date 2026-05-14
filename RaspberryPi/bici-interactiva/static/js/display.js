const body = document.body;

const video = document.getElementById("mainVideo");

// GAME UI
const gameName = document.getElementById("gameName");
const gameScore = document.getElementById("gameScore");
const gameRankPosition = document.getElementById("gameRankPosition");
const gameNearbyRankingList = document.getElementById("gameNearbyRankingList");

// RULETA
const rouletteWheel = document.getElementById("rouletteWheel");

// RECOMMENDATION UI
const recommendationScoreText = document.getElementById("recommendationScoreText");

// RESULT UI
const resultName = document.getElementById("resultName");
const resultRank = document.getElementById("resultRank");
const resultRankingList = document.getElementById("resultRankingList");

const IDLE_VIDEO = "/static/videos/idle.mp4";
const GAME_VIDEO = "/static/videos/game.mp4";

// Debe coincidir con la espera del ESP32
const GAME_UI_DELAY_MS = 7000;

// game.mp4 ahora dura 1 minuto 7 segundos
const GAME_DURATION_MS = 67000;

// La ruleta se detiene 2 segundos antes de terminar game.mp4
const ROULETTE_STOP_BEFORE_END_MS = 2000;
const ROULETTE_STOP_AT_MS = GAME_DURATION_MS - ROULETTE_STOP_BEFORE_END_MS;

// Texto sobre el video de recomendación
const RECOMMENDATION_SCORE_SHOW_MS = 1500;
const RECOMMENDATION_SCORE_HIDE_MS = 3000;

// Giro visual
const ROULETTE_SPINS = 11;

let currentMode = "idle";
let gameUiTimer = null;
let rouletteStopTimer = null;

let recommendationShowTimer = null;
let recommendationHideTimer = null;

let currentRecommendationVideo = "";
let currentRouletteFinalAngle = 0;
let lastFinalScore = 0;


function formatScore(value) {
  return String(Number(value || 0)).padStart(4, "0");
}


function clearGameTimers() {
  if (gameUiTimer) {
    clearTimeout(gameUiTimer);
    gameUiTimer = null;
  }

  if (rouletteStopTimer) {
    clearTimeout(rouletteStopTimer);
    rouletteStopTimer = null;
  }
}


function clearRecommendationTimers() {
  if (recommendationShowTimer) {
    clearTimeout(recommendationShowTimer);
    recommendationShowTimer = null;
  }

  if (recommendationHideTimer) {
    clearTimeout(recommendationHideTimer);
    recommendationHideTimer = null;
  }
}


function resetRoulette() {
  if (!rouletteWheel) return;

  rouletteWheel.classList.remove("roulette-spinning");
  rouletteWheel.style.transition = "none";
  rouletteWheel.style.transform = "rotate(0deg)";

  // Fuerza reflow. Sí, el navegador exige pequeños rituales.
  void rouletteWheel.offsetWidth;
}


function startRouletteSpin() {
  if (!rouletteWheel) return;

  rouletteWheel.classList.remove("roulette-stopped");
  rouletteWheel.style.transition = "none";
  rouletteWheel.style.transform = "rotate(0deg)";
  void rouletteWheel.offsetWidth;

  rouletteWheel.classList.add("roulette-spinning");
}


function stopRouletteAt(angle) {
  if (!rouletteWheel) return;

  rouletteWheel.classList.remove("roulette-spinning");

  const finalAngle = (ROULETTE_SPINS * 360) + Number(angle || 0);

  rouletteWheel.style.transition = "transform 1800ms cubic-bezier(0.12, 0.78, 0.18, 1)";
  rouletteWheel.style.transform = `rotate(${finalAngle}deg)`;
  rouletteWheel.classList.add("roulette-stopped");
}


function scheduleGameUiAndRoulette() {
  body.classList.remove("game-ui-visible");

  clearGameTimers();
  resetRoulette();

  // A los 7 segundos aparecen textos y ruleta
  gameUiTimer = setTimeout(() => {
    if (currentMode === "game") {
      body.classList.add("game-ui-visible");
      startRouletteSpin();
    }
  }, GAME_UI_DELAY_MS);

  // A los 65 segundos desde que empezó game.mp4, la ruleta se detiene.
  rouletteStopTimer = setTimeout(() => {
    if (currentMode === "game") {
      stopRouletteAt(currentRouletteFinalAngle);
    }
  }, ROULETTE_STOP_AT_MS);
}


function playIdle() {
  currentMode = "idle";

  clearGameTimers();
  clearRecommendationTimers();

  body.classList.remove(
    "game-mode",
    "recommendation-mode",
    "result-mode",
    "game-ui-visible",
    "recommendation-score-visible"
  );
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

  clearRecommendationTimers();

  body.classList.remove(
    "idle-mode",
    "recommendation-mode",
    "result-mode",
    "game-ui-visible",
    "recommendation-score-visible"
  );
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

  scheduleGameUiAndRoulette();
}


function playRecommendation() {
  currentMode = "recommendation";

  clearGameTimers();
  clearRecommendationTimers();

  body.classList.remove("idle-mode", "game-mode", "result-mode", "game-ui-visible");
  body.classList.add("recommendation-mode");
  body.classList.remove("recommendation-score-visible");

  video.style.display = "block";
  video.loop = false;

  const src = currentRecommendationVideo || "/static/videos/recomendacion1.mp4";

  if (!video.src.endsWith(src)) {
    video.src = src;
  }

  video.currentTime = 0;

  if (recommendationScoreText) {
    recommendationScoreText.textContent = `Hiciste ${formatScore(lastFinalScore)} puntos`;
  }

  recommendationShowTimer = setTimeout(() => {
    if (currentMode === "recommendation") {
      body.classList.add("recommendation-score-visible");
    }
  }, RECOMMENDATION_SCORE_SHOW_MS);

  recommendationHideTimer = setTimeout(() => {
    if (currentMode === "recommendation") {
      body.classList.remove("recommendation-score-visible");
    }
  }, RECOMMENDATION_SCORE_HIDE_MS);

  video.play().catch((error) => {
    console.error("No se pudo reproducir recomendación:", error);
  });
}


function playResult() {
  currentMode = "result";

  clearGameTimers();
  clearRecommendationTimers();

  body.classList.remove(
    "idle-mode",
    "game-mode",
    "recommendation-mode",
    "game-ui-visible",
    "recommendation-score-visible"
  );
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


async function notifyRecommendationEnded() {
  try {
    await fetch("/api/recommendation-ended", {
      method: "POST",
      cache: "no-store"
    });
  } catch (error) {
    console.error("No se pudo avisar fin de recomendación:", error);
  }
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

    // RULETA / RECOMENDACIÓN
    currentRecommendationVideo = data.recommendation_video || "";
    currentRouletteFinalAngle = Number(data.roulette_final_angle || 0);

    // RESULT DATA
    renderResultPanel(data.last_result_panel);

    if (data.last_result_panel && data.last_result_panel.score !== undefined) {
      lastFinalScore = Number(data.last_result_panel.score || 0);
    }

    const serverMode = data.screen_mode || "idle";

    if (serverMode === "game" && currentMode !== "game") {
      playGame();
    } else if (serverMode === "recommendation" && currentMode !== "recommendation") {
      playRecommendation();
    } else if (serverMode === "result" && currentMode !== "result") {
      playResult();
    } else if (serverMode === "idle" && currentMode !== "idle") {
      playIdle();
    }

  } catch (error) {
    console.error("No se pudo leer /api/state", error);
  }
}


video.addEventListener("ended", () => {
  if (currentMode === "recommendation") {
    notifyRecommendationEnded();
  }
});


setInterval(updateStateFromServer, 100);

playIdle();
updateStateFromServer();