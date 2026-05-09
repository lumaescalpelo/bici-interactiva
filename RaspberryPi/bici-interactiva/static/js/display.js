const body = document.body;

const video = document.getElementById("mainVideo");
const speed = document.getElementById("speed");
const score = document.getElementById("score");
const nameLabel = document.getElementById("name");
const rankingList = document.getElementById("rankingList");
const rankPosition = document.getElementById("rankPosition");

const IDLE_VIDEO = "/static/videos/idle.mp4";
const GAME_VIDEO = "/static/videos/game.mp4";

let localGameActive = false;
let serverGameActive = false;


function playIdle() {
  localGameActive = false;

  body.classList.remove("game-mode");
  body.classList.add("idle-mode");

  video.loop = true;

  if (!video.src.endsWith(IDLE_VIDEO)) {
    video.src = IDLE_VIDEO;
  }

  video.play().catch((error) => {
    console.error("No se pudo reproducir idle:", error);
  });
}


function playGame() {
  localGameActive = true;

  body.classList.remove("idle-mode");
  body.classList.add("game-mode");

  video.loop = false;

  if (!video.src.endsWith(GAME_VIDEO)) {
    video.src = GAME_VIDEO;
  }

  video.currentTime = 0;

  video.play().catch((error) => {
    console.error("No se pudo reproducir game:", error);
  });
}


function formatScore(value) {
  return String(Number(value || 0)).padStart(4, "0");
}


function renderRanking(ranking, currentRank) {
  rankingList.innerHTML = "";

  if (!Array.isArray(ranking) || ranking.length === 0) {
    const item = document.createElement("li");
    item.textContent = "Sin registros";
    rankingList.appendChild(item);

    rankPosition.textContent = "--";
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

    rankingList.appendChild(item);
  });

  if (currentRank !== null && currentRank !== undefined) {
    rankPosition.textContent = `#${currentRank}`;
  } else {
    rankPosition.textContent = "--";
  }
}


async function updateStateFromServer() {
  try {
    const response = await fetch("/api/state", {
      cache: "no-store"
    });

    const data = await response.json();

    nameLabel.textContent = data.participant_name || "PARTICIPANTE";

    const speedValue = Number(data.speed || 0);
    const scoreValue = Number(data.score || 0);

    speed.textContent = `${speedValue.toFixed(1)} km/h`;
    score.textContent = `${formatScore(scoreValue)} pts`;

    renderRanking(data.ranking || [], data.current_rank);

    serverGameActive = Boolean(data.game_active);

    if (serverGameActive && !localGameActive) {
      playGame();
    }

    if (!serverGameActive && localGameActive) {
      playIdle();
    }

  } catch (error) {
    console.error("No se pudo leer /api/state", error);
  }
}


video.addEventListener("ended", () => {
  if (localGameActive && !serverGameActive) {
    playIdle();
  }
});


// Tecla de prueba local.
// Ya que el serial funciona, puedes dejarla comentada.
/*
document.addEventListener("keydown", (event) => {
  if (event.code === "Space" && !localGameActive) {
    playGame();
  }
});
*/


setInterval(updateStateFromServer, 100);

playIdle();
updateStateFromServer();