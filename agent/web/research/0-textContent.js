function extractPageTextObjects() {
	const results = [];
	const seen = new Set();

	// Walk all elements except scripts/styles
	document.body.querySelectorAll("*:not(script):not(sytle)").forEach((el) => {
		const txt = el.textContent.trim();
		if (!txt || seen.has(txt)) return; // skip empty or already seen
		seen.add(txt);
		results.push({ text: txt, element: el });
	});

	return results;
}

// Example usage
const textObjects = extractPageTextObjects();
console.log(textObjects);
