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
const recommendationRankText = document.getElementById("recommendationRankText");
const recommendationRankingList = document.getElementById("recommendationRankingList");

// RESULT UI
// Ya no se muestra después de recomendación, pero se sigue usando para conservar datos
// y no andar rompiendo cosas porque sí. Qué concepto tan revolucionario.
const resultName = document.getElementById("resultName");
const resultRank = document.getElementById("resultRank");
const resultRankingList = document.getElementById("resultRankingList");

const IDLE_VIDEO = "/static/videos/idle.mp4";
const GAME_VIDEO = "/static/videos/game.mp4";

// Debe coincidir con la espera del ESP32
const GAME_UI_DELAY_MS = 7000;

// game.mp4 dura 1 minuto 7 segundos
const GAME_DURATION_MS = 67000;

// La ruleta se detiene 2 segundos antes de terminar game.mp4
const ROULETTE_STOP_BEFORE_END_MS = 2000;
const ROULETTE_STOP_AT_MS = GAME_DURATION_MS - ROULETTE_STOP_BEFORE_END_MS;

// Texto sobre el video de recomendación
const RECOMMENDATION_SCORE_SHOW_MS = 1500;
const RECOMMENDATION_SCORE_HIDE_MS = 3000;

// Velocidad mínima para considerar que sí está pedaleando
const ROULETTE_MIN_SPEED_KMH = 0.8;

// Conversión velocidad bicicleta → velocidad angular ruleta
const ROULETTE_DEG_PER_SEC_PER_KMH = 34;
const ROULETTE_MAX_DEG_PER_SEC = 1500;

// Giro extra visual para el frenado final
const ROULETTE_FINAL_SPINS = 5;

let currentMode = "idle";
let gameUiTimer = null;
let rouletteStopTimer = null;

let recommendationShowTimer = null;
let recommendationHideTimer = null;

let currentRecommendationVideo = "";
let currentRouletteFinalAngle = 0;
let lastFinalScore = 0;
let lastFinalRank = null;
let lastResultPanel = null;

let currentSpeedSmooth = 0;

let rouletteAnimationFrame = null;
let rouletteAngle = 0;
let rouletteLastFrameTime = null;
let rouletteStopped = false;


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


function stopRouletteAnimationLoop() {
  if (rouletteAnimationFrame) {
    cancelAnimationFrame(rouletteAnimationFrame);
    rouletteAnimationFrame = null;
  }

  rouletteLastFrameTime = null;
}


function resetRoulette() {
  if (!rouletteWheel) return;

  stopRouletteAnimationLoop();

  rouletteStopped = false;
  rouletteAngle = 0;

  rouletteWheel.style.transition = "none";
  rouletteWheel.style.transform = "rotate(0deg)";

  void rouletteWheel.offsetWidth;
}


function startRouletteMotionLoop() {
  if (!rouletteWheel) return;

  stopRouletteAnimationLoop();

  rouletteLastFrameTime = performance.now();

  function frame(now) {
    if (currentMode !== "game" || rouletteStopped) {
      rouletteAnimationFrame = null;
      return;
    }

    const deltaSeconds = Math.max(0, (now - rouletteLastFrameTime) / 1000);
    rouletteLastFrameTime = now;

    const speed = Number(currentSpeedSmooth || 0);

    if (speed >= ROULETTE_MIN_SPEED_KMH) {
      const degreesPerSecond = Math.min(
        ROULETTE_MAX_DEG_PER_SEC,
        speed * ROULETTE_DEG_PER_SEC_PER_KMH
      );

      rouletteAngle = (rouletteAngle + degreesPerSecond * deltaSeconds) % 360;

      rouletteWheel.style.transition = "none";
      rouletteWheel.style.transform = `rotate(${rouletteAngle}deg)`;
    }

    rouletteAnimationFrame = requestAnimationFrame(frame);
  }

  rouletteAnimationFrame = requestAnimationFrame(frame);
}


function stopRouletteAt(angle) {
  if (!rouletteWheel) return;

  rouletteStopped = true;
  stopRouletteAnimationLoop();

  const normalizedCurrent = rouletteAngle % 360;
  const target = Number(angle || 0) % 360;

  let delta = target - normalizedCurrent;

  if (delta < 0) {
    delta += 360;
  }

  const finalAngle = rouletteAngle + (ROULETTE_FINAL_SPINS * 360) + delta;

  rouletteAngle = finalAngle;

  rouletteWheel.style.transition = "transform 1800ms cubic-bezier(0.12, 0.78, 0.18, 1)";
  rouletteWheel.style.transform = `rotate(${finalAngle}deg)`;
}


function scheduleGameUiAndRoulette() {
  body.classList.remove("game-ui-visible");

  clearGameTimers();
  resetRoulette();

  gameUiTimer = setTimeout(() => {
    if (currentMode === "game") {
      body.classList.add("game-ui-visible");
      startRouletteMotionLoop();
    }
  }, GAME_UI_DELAY_MS);

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
  stopRouletteAnimationLoop();

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


function renderRecommendationRanking(panel) {
  if (!recommendationRankingList) return;

  recommendationRankingList.innerHTML = "";

  if (!panel || !Array.isArray(panel.entries) || panel.entries.length === 0) {
    return;
  }

  panel.entries.forEach((entry) => {
    const item = document.createElement("li");

    const rank = document.createElement("span");
    rank.className = "recommendation-ranking-rank";
    rank.textContent = `${entry.rank}.`;

    const name = document.createElement("span");
    name.className = "recommendation-ranking-name";
    name.textContent = entry.participant_name || "PARTICIPANTE";

    const points = document.createElement("span");
    points.className = "recommendation-ranking-score";
    points.textContent = formatScore(entry.score);

    item.appendChild(rank);
    item.appendChild(name);
    item.appendChild(points);

    if (entry.is_current) {
      item.classList.add("current-player");
    }

    recommendationRankingList.appendChild(item);
  });
}


function playRecommendation() {
  currentMode = "recommendation";

  clearGameTimers();
  clearRecommendationTimers();
  stopRouletteAnimationLoop();

  body.classList.remove(
    "idle-mode",
    "game-mode",
    "result-mode",
    "game-ui-visible",
    "recommendation-score-visible"
  );
  body.classList.add("recommendation-mode");

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

  if (recommendationRankText) {
    recommendationRankText.textContent = lastFinalRank ? `#${lastFinalRank}` : "#--";
  }

  renderRecommendationRanking(lastResultPanel);

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
  stopRouletteAnimationLoop();

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
  lastResultPanel = panel;

  resultRankingList.innerHTML = "";

  if (!panel) {
    resultName.textContent = "PARTICIPANTE";
    resultRank.textContent = "--";
    lastFinalScore = 0;
    lastFinalRank = null;
    return;
  }

  resultName.textContent = panel.participant_name || "PARTICIPANTE";
  resultRank.textContent = panel.rank ? `#${panel.rank}` : "--";

  if (panel.score !== undefined) {
    lastFinalScore = Number(panel.score || 0);
  }

  if (panel.rank !== undefined && panel.rank !== null) {
    lastFinalRank = Number(panel.rank);
  }

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

    currentSpeedSmooth = Number(data.speed_smooth || data.speed || 0);

    gameName.textContent = data.participant_name || "PARTICIPANTE";
    gameScore.textContent = `${formatScore(data.score || 0)} pts`;

    const rank = data.nearby_current_rank || data.current_rank;
    gameRankPosition.textContent = rank ? `#${rank}` : "--";

    renderNearbyRanking(data.nearby_ranking || []);

    currentRecommendationVideo = data.recommendation_video || "";
    currentRouletteFinalAngle = Number(data.roulette_final_angle || 0);

    renderResultPanel(data.last_result_panel);

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