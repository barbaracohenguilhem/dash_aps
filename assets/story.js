/* Navigation only: hashes and scrolling never change the analytical filters. */
(function () {
  function setup() {
    const nav = document.getElementById("story-nav");
    if (!nav || nav.dataset.ready) return Boolean(nav);
    nav.dataset.ready = "true";
    const links = Array.from(nav.querySelectorAll("[data-story-target]"));
    const workspaceLinks = Array.from(document.querySelectorAll('.topbar-nav a[href^="#"]'));
    let scheduled = false;

    function markSection() {
      scheduled = false;
      const threshold = nav.getBoundingClientRect().height + 48;
      let active = links[0];
      for (const link of links) {
        const target = document.getElementById(link.dataset.storyTarget);
        if (target && target.getBoundingClientRect().top <= threshold) active = link;
      }
      // The final section may be too short to reach the sticky-nav threshold.
      const atBottom = window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2;
      const workspaceThreshold = atBottom ? window.innerHeight : threshold;
      let current = workspaceLinks[0];
      let nearestTop = -Infinity;
      for (const link of workspaceLinks) {
        const target = document.getElementById(link.hash.slice(1));
        const top = target ? target.getBoundingClientRect().top : Infinity;
        if (top <= workspaceThreshold && top > nearestTop) {
          current = link;
          nearestTop = top;
        }
      }
      for (const link of workspaceLinks) {
        if (link === current) link.setAttribute("aria-current", "location");
        else link.removeAttribute("aria-current");
      }
      for (const link of links) {
        if (link === active) link.setAttribute("aria-current", "step");
        else link.removeAttribute("aria-current");
      }
    }
    function schedule() {
      if (!scheduled) {
        scheduled = true;
        requestAnimationFrame(markSection);
      }
    }
    window.addEventListener("scroll", schedule, {passive: true});
    window.addEventListener("resize", schedule);
    // Filters can change document height without a scroll event.
    if (window.ResizeObserver) new ResizeObserver(schedule).observe(document.querySelector("main"));
    markSection();
    return true;
  }

  if (!setup()) {
    const observer = new MutationObserver(function () {
      if (setup()) observer.disconnect();
    });
    observer.observe(document.documentElement, {childList: true, subtree: true});
  }

  // Hash links into the optional atlas must reveal it before scrolling.
  document.addEventListener("click", function (event) {
    const anchor = event.target.closest('a[href^="#"]');
    if (!anchor) return;
    const target = document.getElementById(anchor.getAttribute("href").slice(1));
    if (!target) return;
    let parent = target.parentElement;
    while (parent) {
      if (parent.tagName === "DETAILS") parent.open = true;
      parent = parent.parentElement;
    }
  });
  document.addEventListener("toggle", function (event) {
    if (event.target.matches("details.atlas") && event.target.open) {
      requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
    }
  }, true);

  document.addEventListener("click", function (event) {
    const button = event.target.closest("[data-table-scroll]");
    if (!button) return;
    const table = document.querySelector("#tabela-vagas .dash-spreadsheet-container");
    if (!table) return;
    table.scrollBy({
      left: Number(button.dataset.tableScroll) * table.clientWidth * 0.75,
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
    });
  });
})();
