// Paste in console for a one-off highlight
(function () {
	let node = document.querySelector('[id^="cf-chl-widget-"][type="hidden"]');
	if (!node) return console.warn("No Turnstile placeholder found");

	// Walk upward until we hit the first element that really renders
	while (node && (node.offsetWidth === 0 || node.offsetHeight === 0)) {
		node = node.parentElement;
	}
	if (!node) return console.warn("Visible widget not found");

	// Style it
	node.style.outline = "3px solid #e63946";
	node.style.borderRadius = "6px";
	node.scrollIntoView({ behavior: "smooth", block: "center" });

	console.log("✔ Highlighted the visible Turnstile wrapper:", node);
})();
