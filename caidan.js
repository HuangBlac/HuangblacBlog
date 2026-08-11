(function () {
  const correctSequence = [3, 1, 4, 5, 2, 6];
  const buttons = Array.from(document.querySelectorAll("[data-puzzle-key]"));
  const status = document.querySelector("[data-puzzle-status]");
  let progress = 0;
  let unlocked = false;

  if (!buttons.length || !status) return;

  function resetPuzzle(showHint) {
    progress = 0;
    buttons.forEach((button) => {
      button.disabled = false;
      button.classList.remove("is-correct");
    });

    status.textContent = showHint
      ? "门后似乎传来一点动静，但顺序不对，它又安静了。"
      : "六句话里藏着一条路。顺序比点击次数重要。";
  }

  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      if (unlocked) return;

      const key = Number(button.dataset.puzzleKey);
      if (key !== correctSequence[progress]) {
        resetPuzzle(progress > 0);
        return;
      }

      button.disabled = true;
      button.classList.add("is-correct");
      progress += 1;

      if (progress < correctSequence.length) {
        status.textContent = `锁里传来第 ${progress} 声轻响。`;
        return;
      }

      unlocked = true;
      document.body.classList.add("secret-unlocked");
      status.textContent = "门开了。正在前往闭店以后的房间……";
      window.setTimeout(() => {
        window.location.assign("after-hours.html");
      }, 850);
    });
  });

  resetPuzzle(false);
})();
