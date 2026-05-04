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
      <section class="game-stage">
        <div class="question-chip">Rainbow Round</div>
        <h2>Question ${data.number} of ${data.total}</h2>
        <p class="question-meta">Keep the streak going.</p>
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

function showError(message) {
  const container = document.getElementById("game");

  container.innerHTML = `
    <section class="error-stage">
      <div class="error-chip">Something went wrong</div>
      <p class="error-message">${message}</p>
    </section>
  `;
}
