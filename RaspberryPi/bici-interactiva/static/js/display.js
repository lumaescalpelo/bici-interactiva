const video = document.getElementById("mainVideo");
const hint = document.getElementById("hint");
const speed = document.getElementById("speed");
const score = document.getElementById("score");
const nameLabel = document.getElementById("name");

const IDLE_VIDEO = "/static/videos/idle.mp4";
const GAME_VIDEO = "/static/videos/game.mp4";

let localGameActive = false;
let serverGameActive = false;


function playIdle() {
  localGameActive = false;

  video.loop = true;

  if (!video.src.endsWith(IDLE_VIDEO)) {
    video.src = IDLE_VIDEO;
  }

  video.play().catch((error) => {
    console.error("No se pudo reproducir idle:", error);
  });

  hint.textContent = "ESPERANDO PARTICIPANTE";
}


function playGame() {
  localGameActive = true;

  video.loop = false;

  if (!video.src.endsWith(GAME_VIDEO)) {
    video.src = GAME_VIDEO;
  }

  video.currentTime = 0;

  video.play().catch((error) => {
    console.error("No se pudo reproducir game:", error);
  });

  hint.textContent = "PRUEBA EN CURSO";
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
    score.textContent = `${String(scoreValue).padStart(4, "0")} pts`;

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


// Si el video termina antes de que llegue END,
// lo dejamos visualmente en idle.
// En operación normal, END debe llegar desde ESP32.
video.addEventListener("ended", () => {
  if (localGameActive && !serverGameActive) {
    playIdle();
  }
});


// Tecla de prueba local.
// La puedes comentar cuando ya no la necesites.
document.addEventListener("keydown", (event) => {
  if (event.code === "Space" && !localGameActive) {
    playGame();
  }
});


// Actualización rápida para que velocidad y puntaje se sientan vivos.
// 100 ms = 10 Hz, igual que ESP32.
setInterval(updateStateFromServer, 100);

playIdle();
updateStateFromServer();