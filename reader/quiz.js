"use strict";

const quiz$ = (id) => document.getElementById(id);
const storyId = new URLSearchParams(window.location.search).get("story");
let reviewQueue = [];
let currentIndex = 0;
let currentWord = null;
let answerPending = false;

function showQuizError(message) {
  const error = quiz$("quiz-error");
  error.textContent = message;
  error.hidden = false;
}

function renderQuestion() {
  answerPending = false;
  currentWord = reviewQueue[currentIndex];
  if (!currentWord) {
    quiz$("quiz").replaceChildren();
    const empty = document.createElement("p");
    empty.textContent = "No words are due for review.";
    quiz$("quiz").append(empty);
    return;
  }
  quiz$("quiz-progress").textContent = `Card ${currentIndex + 1} of ${reviewQueue.length}`;
  quiz$("quiz-prompt").textContent = currentWord.lemma;
  quiz$("quiz-source").textContent = currentWord.meaningSource === "dictionary"
    ? "Dictionary glosses"
    : currentWord.meaningSource === "machine translation"
      ? "Isolated machine translation (dictionary entry unavailable)"
      : "Meaning unavailable";
  quiz$("quiz-surface").textContent = currentWord.surface !== currentWord.lemma
    ? `Seen as: ${currentWord.surface}` : "";
  quiz$("quiz-meaning").textContent = currentWord.meaning;
  quiz$("quiz-answer").hidden = true;
  quiz$("reveal-answer").hidden = false;
}

function answerCurrentWord(remembered) {
  if (!currentWord || answerPending) return;
  answerPending = true;
  try {
    updateWordSRSResult(currentWord.lemma, remembered);
    currentIndex += 1;
    renderQuestion();
  } catch (err) {
    answerPending = false;
    showQuizError(`Could not save your answer: ${err.message}`);
  }
}

function initQuiz() {
  try {
    reviewQueue = getDueWords(storyId);
    quiz$("reveal-answer").addEventListener("click", () => {
      quiz$("quiz-answer").hidden = false;
      quiz$("reveal-answer").hidden = true;
    });
    quiz$("remembered").addEventListener("click", () => answerCurrentWord(true));
    quiz$("forgotten").addEventListener("click", () => answerCurrentWord(false));
    renderQuestion();
  } catch (err) {
    showQuizError(`Could not load review words: ${err.message}`);
    quiz$("quiz").hidden = true;
  }
}

initQuiz();
