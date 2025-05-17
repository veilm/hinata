// Helper function to process a single element node and its children recursively
function processElementNode(element) {
	// Skip script and style elements as they don't represent visible content
	// Note: The original selector had a typo "sytle" which is corrected here.
	if (element.tagName === "SCRIPT" || element.tagName === "STYLE") {
		return null;
	}

	// Basic heuristic for visibility:
	// Elements like <meta>, <link> in <body>, or elements with `display: none` might be skipped
	// by more advanced checks. For now, primary filtering is by tag type (script/style).
	// An element being 'offsetParent === null' isn't a foolproof invisibility check
	// (e.g. position:fixed elements, or the <html> element itself).
	// The main goal here is to get structural text content.
	// If an element is not a script/style, we attempt to process it.
	// It will be pruned later if it and its children yield no text content.

	const nodeInfo = {
		tagName: element.tagName.toLowerCase(),
		attributes: {},
		textNodes: [], // For direct text content (text nodes) of this element
		children: [], // For processed child elements that form the subtree
	};

	// Gather element attributes
	for (const attr of element.attributes) {
		nodeInfo.attributes[attr.name] = attr.value;
	}

	// Process child nodes
	for (const child of element.childNodes) {
		if (child.nodeType === Node.TEXT_NODE) {
			// Handle text nodes
			const text = child.nodeValue.trim();
			if (text) {
				nodeInfo.textNodes.push(text);
			}
		} else if (child.nodeType === Node.ELEMENT_NODE) {
			// Handle element nodes recursively
			const childElementOutput = processElementNode(child);
			if (childElementOutput) {
				// Add to children if the recursive call produced a meaningful output
				nodeInfo.children.push(childElementOutput);
			}
		}
		// Other node types (comments, etc.) are ignored
	}

	// Only return the node representation if it contains direct text
	// or has children that themselves contain content. This prunes empty branches.
	if (nodeInfo.textNodes.length > 0 || nodeInfo.children.length > 0) {
		return nodeInfo;
	}

	// This element (and its subtree, if no content was found) is considered empty or irrelevant
	return null;
}

// Main function to extract page content as a tree structure
function extractPageContentTree() {
	// Start processing from document.body, as it's the typical container for page content
	if (!document.body) {
		console.warn(
			"document.body is not available. Cannot extract content tree.",
		);
		return null;
	}
	// The root of our content tree will be the processed body element
	return processElementNode(document.body);
}

// Example usage:
const contentTree = extractPageContentTree();

// To inspect the tree, you can log it directly or serialize it to JSON.
// For a more readable output, especially for large trees, JSON.stringify is useful.
if (contentTree) {
	// Using JSON.stringify with an indenting factor (e.g., 2) for pretty printing.
	console.log(JSON.stringify(contentTree, null, 2));
} else {
	console.log(
		"No content tree was extracted (e.g., body is empty or contains only scripts/styles).",
	);
}
