// Markdown rendering utilities
export { escapeHtml, renderMarkdown };
function escapeHtml(unsafe) {
	if (unsafe === null || unsafe === undefined) return "";
	return unsafe
		.toString()
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;")
		.replace(/'/g, "&#039;");
}

// Simple character-by-character markdown parser for bold and italic
function parseMarkdownSimple(text) {
	let result = [];
	let i = 0;

	// Current state
	let inBold = false;
	let inItalic = false;
	let boldMarker = null; // Track which marker opened bold ('*' or '_')
	let italicMarker = null; // Track which marker opened italic

	while (i < text.length) {
		const char = text[i];
		const nextChar = i + 1 < text.length ? text[i + 1] : null;
		const prevChar = i > 0 ? text[i - 1] : null;

		if (char === "*" || char === "_") {
			// Count consecutive markers
			let markerCount = 1;
			let j = i + 1;
			while (j < text.length && text[j] === char) {
				markerCount++;
				j++;
			}

			// Handle based on marker count
			if (markerCount >= 3) {
				// Triple marker - could be bold+italic
				if (
					inBold &&
					inItalic &&
					boldMarker === char &&
					italicMarker === char
				) {
					// Close both
					result.push("</em></strong>");
					inBold = false;
					inItalic = false;
					boldMarker = null;
					italicMarker = null;
					i += 3;
					continue;
				} else if (!inBold && !inItalic) {
					// Open both
					result.push("<strong><em>");
					inBold = true;
					inItalic = true;
					boldMarker = char;
					italicMarker = char;
					i += 3;
					continue;
				}
			}

			if (markerCount >= 2) {
				// Bold marker
				if (inBold && boldMarker === char) {
					// Close bold
					result.push("</strong>");
					inBold = false;
					boldMarker = null;
					i += 2;
					continue;
				} else if (!inBold) {
					// Open bold
					result.push("<strong>");
					inBold = true;
					boldMarker = char;
					i += 2;
					continue;
				}
			}

			// Single marker (italic) - only if we have exactly 1
			if (markerCount === 1) {
				if (char === "_") {
					const atStart = i === 0 || /\s/.test(prevChar);
					const nextIsSpace = !nextChar || /\s/.test(nextChar);

					if (inItalic && italicMarker === "_") {
						// Closing underscore italic - check we're at end of word
						const afterIsSpace = i + 1 >= text.length || /\s/.test(text[i + 1]);
						if (afterIsSpace || /[^\w]/.test(text[i + 1])) {
							result.push("</em>");
							inItalic = false;
							italicMarker = null;
							i++;
							continue;
						}
					} else if (!inItalic && atStart && !nextIsSpace) {
						// Opening underscore italic
						result.push("<em>");
						inItalic = true;
						italicMarker = "_";
						i++;
						continue;
					}
				} else if (char === "*") {
					// Check if this is a literal asterisk (surrounded by spaces)
					const beforeSpace = i === 0 || /\s/.test(text[i - 1]);
					const afterSpace = i + 1 >= text.length || /\s/.test(text[i + 1]);

					if (beforeSpace && afterSpace) {
						// Literal asterisk - skip formatting
					} else if (inItalic && italicMarker === "*") {
						// Check if valid closing (not preceded by space)
						if (!beforeSpace) {
							// Close italic
							result.push("</em>");
							inItalic = false;
							italicMarker = null;
							i++;
							continue;
						}
					} else if (!inItalic && !afterSpace) {
						// Open italic (not followed by space)
						result.push("<em>");
						inItalic = true;
						italicMarker = "*";
						i++;
						continue;
					}
				}
			}
		}

		// Regular character
		result.push(char);
		i++;
	}

	// Close any unclosed tags
	if (inItalic) result.push("</em>");
	if (inBold) result.push("</strong>");

	return result.join("");
}

function parseMarkdownTables(text, inlineCode) {
	const tables = [];
	const lines = text.split("\n");
	const output = [];

	function isTableSeparator(line) {
		return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
	}

	function isTableHeader(line) {
		return line.includes("|") && line.trim() && !isTableSeparator(line);
	}

	function splitRow(line) {
		let row = line.trim();
		if (row.startsWith("|")) row = row.slice(1);
		if (row.endsWith("|")) row = row.slice(0, -1);
		return row.split("|").map((cell) => cell.trim());
	}

	function normalizeRow(row, colCount) {
		const normalized = row.slice(0, colCount);
		while (normalized.length < colCount) normalized.push("");
		return normalized;
	}

	function restoreInlineCode(textValue) {
		if (!inlineCode || inlineCode.length === 0) return textValue;
		let restored = textValue;
		inlineCode.forEach((code, i) => {
			restored = restored.replace(`\x00INLINE_CODE_${i}\x00`, code);
		});
		return restored;
	}

	function renderTable(headerCells, bodyRows) {
		const colCount = Math.max(
			headerCells.length,
			...bodyRows.map((row) => row.length),
			1,
		);
		const normalizedHeader = normalizeRow(headerCells, colCount);
		const normalizedRows = bodyRows.map((row) => normalizeRow(row, colCount));

		const thead =
			"<thead><tr>" +
			normalizedHeader
				.map((cell) => `<th>${parseMarkdownSimple(cell)}</th>`)
				.join("") +
			"</tr></thead>";
		const tbodyRows = normalizedRows
			.map(
				(row) =>
					"<tr>" +
					row.map((cell) => `<td>${parseMarkdownSimple(cell)}</td>`).join("") +
					"</tr>",
			)
			.join("");
		let tableHtml = `<table>${thead}`;
		if (tbodyRows) tableHtml += `<tbody>${tbodyRows}</tbody>`;
		tableHtml += "</table>";

		return restoreInlineCode(tableHtml);
	}

	for (let i = 0; i < lines.length; i++) {
		const line = lines[i];
		const nextLine = i + 1 < lines.length ? lines[i + 1] : null;

		if (nextLine && isTableHeader(line) && isTableSeparator(nextLine)) {
			const headerCells = splitRow(line);
			const bodyRows = [];
			i += 2;

			while (i < lines.length && lines[i].includes("|") && !isTableSeparator(lines[i])) {
				bodyRows.push(splitRow(lines[i]));
				i++;
			}

			const placeholder = `\x00TABLE_${tables.length}\x00`;
			const needsLeadingBlank =
				output.length > 0 && output[output.length - 1].trim() !== "";
			if (needsLeadingBlank) output.push("");
			output.push(placeholder);

			if (i < lines.length && lines[i].trim() !== "") {
				output.push("");
			}

			tables.push(renderTable(headerCells, bodyRows));
			i -= 1;
			continue;
		}

		output.push(line);
	}

	return { text: output.join("\n"), tables };
}

// Improved markdown renderer
function renderMarkdown(text) {
	// First escape HTML to prevent XSS
	let html = escapeHtml(text);

	// Headers (h1-h6) - do these first
	html = html.replace(/^######\s+(.+)$/gm, "<h6>$1</h6>");
	html = html.replace(/^#####\s+(.+)$/gm, "<h5>$1</h5>");
	html = html.replace(/^####\s+(.+)$/gm, "<h4>$1</h4>");
	html = html.replace(/^###\s+(.+)$/gm, "<h3>$1</h3>");
	html = html.replace(/^##\s+(.+)$/gm, "<h2>$1</h2>");
	html = html.replace(/^#\s+(.+)$/gm, "<h1>$1</h1>");

	// Horizontal rules (*** alone on a line) - handle before code blocks
	html = html.replace(/^\*\*\*$/gm, "<hr>");

	// Code blocks (```) - protect from further processing
	const codeBlocks = [];
	html = html.replace(/```([\s\S]*?)```/g, function (match, code) {
		const placeholder = `\x00CODE_BLOCK_${codeBlocks.length}\x00`;
		codeBlocks.push("<pre><code>" + code + "</code></pre>");
		return placeholder;
	});

	// Inline code (`) - protect from further processing
	const inlineCode = [];
	html = html.replace(/`([^`]+)`/g, function (match, code) {
		const placeholder = `\x00INLINE_CODE_${inlineCode.length}\x00`;
		inlineCode.push("<code>" + code + "</code>");
		return placeholder;
	});

	const tableBlocks = parseMarkdownTables(html, inlineCode);
	html = tableBlocks.text;

	// Parse bold and italic
	html = parseMarkdownSimple(html);

	// Restore code blocks and inline code
	codeBlocks.forEach((code, i) => {
		html = html.replace(`\x00CODE_BLOCK_${i}\x00`, code);
	});
	inlineCode.forEach((code, i) => {
		html = html.replace(`\x00INLINE_CODE_${i}\x00`, code);
	});

	// Line breaks
	html = html.replace(/  \n/g, "<br>\n");

	// Split into paragraphs and wrap properly
	const paragraphs = html.split(/\n\n+/);
	html = paragraphs
		.filter((p) => p.trim()) // Remove empty paragraphs
		.map((p) => `<p>${p}</p>`)
		.join("");

	tableBlocks.tables.forEach((table, i) => {
		const placeholder = `\x00TABLE_${i}\x00`;
		const wrapped = new RegExp(`<p>\\s*${placeholder}\\s*<\\/p>`, "g");
		html = html.replace(wrapped, placeholder);
		html = html.replace(placeholder, table);
	});

	return html;
}
