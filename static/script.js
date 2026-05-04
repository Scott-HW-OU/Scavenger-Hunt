// --------------------------------------------------
// Global State
// --------------------------------------------------

let sessionId = null;

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }

  return response.json();
}

// --------------------------------------------------
// Start Game (called after user enters name/email/city)
// --------------------------------------------------

async function startGame() {
  const name = document.getElementById("name").value;
  const email = document.getElementById("email").value;
  const cityId = document.getElementById("city").value;

  try {
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

    const container = document.getElementById("game");

    container.innerHTML = `
      <h2>Question ${data.number} of ${data.total}</h2>
      <p>${data.question}</p>

      <button onclick="submitAnswer('${data.options[0]}')">${data.options[0]}</button>
      <button onclick="submitAnswer('${data.options[1]}')">${data.options[1]}</button>
      <button onclick="submitAnswer('${data.options[2]}')">${data.options[2]}</button>
      <button onclick="submitAnswer('${data.options[3]}')">${data.options[3]}</button>

      <p id="feedback"></p>
    `;
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
    } else {
      feedback.innerText = `Incorrect. Correct answer was: ${data.correct_answer}`;
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
    <h2>Game Complete</h2>
    <p>Thank you for taking part!</p>
    <p>Your results have been emailed to you.</p>
  `;
}

function showError(message) {
  const container = document.getElementById("game");

  container.innerHTML = `
    <p>${message}</p>
  `;
}
