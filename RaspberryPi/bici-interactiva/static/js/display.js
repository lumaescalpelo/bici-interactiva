const video = document.getElementById("mainVideo");
const hint = document.getElementById("hint");
const speed = document.getElementById("speed");
const score = document.getElementById("score");
const nameLabel = document.getElementById("name");

const IDLE_VIDEO = "/static/videos/idle.mp4";
const GAME_VIDEO = "/static/videos/game.mp4";

let gameActive = false;

function playIdle() {
  gameActive = false;

  video.loop = true;
  video.src = IDLE_VIDEO;
  video.play();

  speed.textContent = "0.0 km/h";
  score.textContent = "0000 pts";
  hint.textContent = "Presiona ESPACIO para iniciar prueba";
}

function playGame() {
  gameActive = true;

  video.loop = false;
  video.src = GAME_VIDEO;
  video.play();

  hint.textContent = "PRUEBA EN CURSO";
}

async function updateStateFromServer() {
  try {
    const response = await fetch("/api/state");
    const data = await response.json();

    nameLabel.textContent = data.participant_name || "PARTICIPANTE";
    speed.textContent = `${Number(data.speed).toFixed(1)} km/h`;
    score.textContent = `${String(data.score).padStart(4, "0")} pts`;

  } catch (error) {
    console.error("No se pudo leer /api/state", error);
  }
}

video.addEventListener("ended", () => {
  if (gameActive) {
    playIdle();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.code === "Space" && !gameActive) {
    playGame();
  }
});

setInterval(updateStateFromServer, 250);

playIdle();
updateStateFromServer();