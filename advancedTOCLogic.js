function openAnElement(elementId, event) {
  const item = document.getElementById(elementId)?.parentElement;
  if (!item) return;

  const children = item.children;
  if (children.length > 0) {
    if (event.target.nodeName === "LI") {
      // you clicked the marker, you want to open/close it
      item.classList.toggle("open");
      return;
    }

    if (!item.classList.contains("open")) {
      item.classList.add("open");
    }
    document
      .querySelectorAll("nav#TOC li")
      .forEach((item) => item.classList.remove("active"));
    item.classList.add("active");
  }
}

function setupOnClickListeners() {
  const TOC = document.querySelectorAll("nav#TOC");
  const TOCItems = document.querySelectorAll("nav#TOC li");

  TOCItems.forEach((item) => {
    item.addEventListener("click", function (event) {
      event.stopPropagation();
      const a = item.querySelector("a");
      openAnElement(a.id, event);
    });
  });
}

function getIdFromURL() {
  let tocId;
  const url = window.location.href;
  if (url.includes("#")) {
    // there is an anchor
    const temporaryId = url.split("#")[1];
    const element = document.getElementById(temporaryId);
    if (element) {
      //the provided id is valid
      if (temporaryId.includes("Table_") || temporaryId.includes("Figure_")) {
        // deduct heading from temporaryId
        const headingId = temporaryId
          .replace("Table_", "")
          .replace("Figure_", "")
          .split("-")[0];
        tocId = `toc-${headingId}`;
      } else {
        // it is a clause
        tocId = `toc-${temporaryId}`;
      }
    }
  } else {
    // no anchor, deduct from filename
    const filename = window.location.pathname.split("/").pop().split(".")[0];
    const topHeadingId = filename.split("-")[1];
    tocId = `toc-${topHeadingId}`;
  }
  return tocId;
}

function scrollToClosestAnchorInTOC() {
  const tocId = getIdFromURL();

  if (tocId) {
    const targetElement = document.getElementById(tocId);
    if (targetElement) {
      targetElement.scrollIntoView();
    }
    localStorage.setItem("scrollTo", tocId);
  } else {
    localStorage.removeItem("scrollTo");
  }
  //   console.log("scrollTo:", localStorage.getItem("scrollTo"));
}

function openCorrectPanelDependingOnStoredElement() {
  const scrollToId = localStorage.getItem("scrollTo");
  if (!scrollToId) {
    return;
  }

  const targetElement = document.getElementById(scrollToId);
  if (!targetElement) {
    return;
  }

  const originalLiElement = targetElement.parentElement;
  if (!originalLiElement) {
    return;
  }

  originalLiElement.classList.add("open");
  originalLiElement.classList.add("active");

  // we are working with li elements, so we skip the ul parent
  let parentElement = originalLiElement.parentElement?.parentElement; // above li element or the nav
  if (!parentElement) {
    return;
  }

  // this handles all the other cases
  while (parentElement && parentElement.id !== "TOC") {
    const aElement = parentElement.querySelector("a");
    if (!aElement) {
      break;
    }

    const parentElementTOCId = aElement.getAttribute("id");
    if (parentElementTOCId) {
      parentElement.classList.add("open");
      // we are working with li elements, so we skip the ul parent
      parentElement = parentElement.parentElement?.parentElement;
    } else {
      break;
    }
  }
}

function fixFaultyTOCText() {
  const tocItems = document.querySelectorAll("nav#TOC a");
  tocItems.forEach((item) => {
    const parent = item.parentElement;
    if (parent.childNodes.length > 1) {
      const secondChildren = parent.childNodes[1];
      if (secondChildren.nodeName === "#text") {
        item.textContent = item.textContent + secondChildren.textContent;
      }
      parent.removeChild(secondChildren);
    }
  });
}

// on dom loaded
document.addEventListener("DOMContentLoaded", function () {
  setupOnClickListeners();
  scrollToClosestAnchorInTOC();
  openCorrectPanelDependingOnStoredElement();
  fixFaultyTOCText();
});

window.addEventListener("popstate", function (event) {
  //   console.log("URL changed via browser navigation:", window.location.href);
  const idFromUrl = getIdFromURL();
  openAnElement(idFromUrl, event);
  scrollToClosestAnchorInTOC();
  openCorrectPanelDependingOnStoredElement();
});
