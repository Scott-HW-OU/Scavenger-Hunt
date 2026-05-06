// --------------------------------------------------
// Global State
// --------------------------------------------------

let sessionId = null;
let pendingQuestion = null;
const DEFAULT_LANDMARK_RADIUS_METERS = 60;

document.addEventListener("DOMContentLoaded", () => {
  loadCities();
});

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }

  return response.json();
}

async function loadCities() {
  const citySelect = document.getElementById("city");

  try {
    const data = await fetchJson("/api/cities");
    const cities = data.cities || [];

    if (cities.length === 0) {
      citySelect.innerHTML = `<option value="">No cities available</option>`;
      citySelect.disabled = true;
      return;
    }

    citySelect.innerHTML = cities
      .map(city => `<option value="${city.id}">${city.name}</option>`)
      .join("");
    citySelect.disabled = false;
  } catch (error) {
    citySelect.innerHTML = `<option value="">Unable to load cities</option>`;
    citySelect.disabled = true;
    showError(error.message);
  }
}

// --------------------------------------------------
// Start Game (called after user enters name/email/city)
// --------------------------------------------------

async function startGame() {
  const name = document.getElementById("name").value;
  const email = document.getElementById("email").value;
  const cityId = document.getElementById("city").value;

  if (!cityId) {
    showError("Please choose a city before starting the game.");
    return;
  }

  try {
    await ensureLocationPermission();

    const data = await fetchJson("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: name,
        email: email,
        city_id: cityId
      })
    });

    sessionId = data.session_id;
    loadQuestion();
  } catch (error) {
    showError(error.message);
  }
}

// --------------------------------------------------
// Load Current Question
// --------------------------------------------------

async function loadQuestion() {
  try {
    const data = await fetchJson(`/api/question/${sessionId}`);

    if (data.error) {
      showCompletion();
      return;
    }

    pendingQuestion = data;
    await showQuestionWhenNearby();
  } catch (error) {
    showError(error.message);
  }
}

// --------------------------------------------------
// Submit Answer
// --------------------------------------------------

async function submitAnswer(answer) {
  try {
    const data = await fetchJson(`/api/answer/${sessionId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer: answer })
    });

    const feedback = document.getElementById("feedback");

    if (data.correct) {
      feedback.innerText = "Correct!";
      feedback.className = "feedback-correct";
    } else {
      feedback.innerText = `Incorrect. Correct answer was: ${data.correct_answer}`;
      feedback.className = "feedback-incorrect";
    }

    if (data.next_step === "next_question") {
      setTimeout(loadQuestion, 1500);
    } else {
      setTimeout(showCompletion, 1500);
    }
  } catch (error) {
    showError(error.message);
  }
}

// --------------------------------------------------
// Completion Screen
// --------------------------------------------------

function showCompletion() {
  const container = document.getElementById("game");

  container.innerHTML = `
    <section class="completion-stage">
      <div class="completion-chip">Finish Line</div>
      <h2>Game Complete</h2>
      <p class="status-copy">Thank you for taking part!</p>
      <p class="status-copy">Your results have been emailed to you.</p>
    </section>
  `;
}

async function ensureLocationPermission() {
  if (!navigator.geolocation) {
    throw new Error("This device does not support location services.");
  }

  await getCurrentPosition();
}

async function showQuestionWhenNearby() {
  if (!pendingQuestion) {
    return;
  }

  const radiusMeters = pendingQuestion.radius_meters || DEFAULT_LANDMARK_RADIUS_METERS;

  if (pendingQuestion.latitude === null || pendingQuestion.longitude === null) {
    showError(`Location data is missing for ${pendingQuestion.landmark_name}. Add coordinates for this landmark in the database.`);
    return;
  }

  const position = await getCurrentPosition();
  const distance = calculateDistanceMeters(
    position.coords.latitude,
    position.coords.longitude,
    pendingQuestion.latitude,
    pendingQuestion.longitude
  );

  if (distance > radiusMeters) {
    showLocationGate(distance, radiusMeters);
    return;
  }

  renderQuestion(pendingQuestion, distance);
}

function renderQuestion(data, distance) {
  const container = document.getElementById("game");
  const distanceLabel = Math.round(distance);

  container.innerHTML = `
    <section class="game-stage">
      <div class="question-chip">Rainbow Round</div>
      <h2>Question ${data.number} of ${data.total}</h2>
      <p class="question-meta">${data.landmark_name} unlocked at ${distanceLabel} meters away.</p>
      <p class="question-copy">${data.question}</p>

      <div class="answers-grid">
        <button class="answer-button" onclick="submitAnswer('${data.options[0]}')">${data.options[0]}</button>
        <button class="answer-button" onclick="submitAnswer('${data.options[1]}')">${data.options[1]}</button>
        <button class="answer-button" onclick="submitAnswer('${data.options[2]}')">${data.options[2]}</button>
        <button class="answer-button" onclick="submitAnswer('${data.options[3]}')">${data.options[3]}</button>
      </div>

      <p id="feedback"></p>
    </section>
  `;
}

function showLocationGate(distance, radiusMeters) {
  const container = document.getElementById("game");
  const roundedDistance = Math.round(distance);

  container.innerHTML = `
    <section class="error-stage">
      <div class="error-chip">Move Closer</div>
      <h2>${pendingQuestion.landmark_name}</h2>
      <p class="error-message">
        You need to be within ${radiusMeters} meters of the landmark to unlock this question.
        You are currently about ${roundedDistance} meters away.
      </p>
      <button class="primary-button" onclick="retryLocationCheck()">Check My Location Again</button>
    </section>
  `;
}

async function retryLocationCheck() {
  try {
    await showQuestionWhenNearby();
  } catch (error) {
    showError(error.message);
  }
}

function getCurrentPosition() {
  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(resolve, () => {
      reject(new Error("Location access is required to play this game."));
    }, {
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 0
    });
  });
}

function calculateDistanceMeters(lat1, lon1, lat2, lon2) {
  const earthRadius = 6371000;
  const toRadians = degrees => degrees * (Math.PI / 180);
  const deltaLat = toRadians(lat2 - lat1);
  const deltaLon = toRadians(lon2 - lon1);
  const startLat = toRadians(lat1);
  const endLat = toRadians(lat2);

  const a = Math.sin(deltaLat / 2) ** 2
    + Math.cos(startLat) * Math.cos(endLat) * Math.sin(deltaLon / 2) ** 2;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

  return earthRadius * c;
}

function showError(message) {
  const container = document.getElementById("game");

  container.innerHTML = `
    <section class="error-stage">
      <div class="error-chip">Something went wrong</div>
      <p class="error-message">${message}</p>
    </section>
  `;
}
