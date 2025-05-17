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

	// NEW HEURISTIC: Collapse wrapper elements
	// An element is a wrapper if it has no direct text nodes and exactly one child element.
	if (nodeInfo.textNodes.length === 0 && nodeInfo.children.length === 1) {
		// Replace the wrapper with its single child.
		// The child has already been processed by a recursive call to processElementNode,
		// so it's already in the desired structured format (or null if it was pruned).
		return nodeInfo.children[0];
	}

	// Original pruning logic (now applied if not a collapsed wrapper):
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

// Helper function to format a node and its children recursively for string output
function formatNodeRecursive(node, indentLevel = 0) {
	let output = "";
	const indent = "\t".repeat(indentLevel);

	// Current node's line
	output += indent + node.tagName;
	if (node.textNodes && node.textNodes.length > 0) {
		// Text nodes are already trimmed and non-empty from processElementNode
		const combinedText = node.textNodes.join(" ");
		if (combinedText) {
			// Still, ensure joined text is not effectively empty
			output += ": " + combinedText;
		}
	}
	output += "\n";

	// Children
	if (node.children && node.children.length > 0) {
		for (const child of node.children) {
			output += formatNodeRecursive(child, indentLevel + 1);
		}
	}
	return output;
}

// Function to format the entire content tree into a string
function formatTreeToString(tree) {
	if (!tree) return "";
	return formatNodeRecursive(tree); // Start recursion with the root of the tree
}

// Function to display the formatted tree in an overlay
function displayTreeOverlay(formattedTreeString) {
	// Guard against trying to use DOM APIs in non-browser environments
	if (typeof document === "undefined" || !document.body) {
		console.warn("DOM environment not available for overlay display.");
		return;
	}
	if (!formattedTreeString) return;

	// Create overlay div
	const overlay = document.createElement("div");
	overlay.id = "dom-tree-overlay";
	Object.assign(overlay.style, {
		position: "fixed",
		top: "0",
		left: "0",
		width: "100vw",
		height: "100vh",
		backgroundColor: "rgba(0, 0, 0, 0.85)",
		zIndex: "2147483647", // High z-index
		padding: "20px",
		boxSizing: "border-box",
		overflowY: "auto", // Enable vertical scroll for overlay content
		color: "white", // Default text color for controls within overlay
	});

	// Create close button
	const closeButton = document.createElement("button");
	closeButton.textContent = "Close Visualization";
	Object.assign(closeButton.style, {
		position: "absolute", // Positioned relative to the overlay
		top: "20px",
		right: "20px",
		padding: "10px 18px",
		cursor: "pointer",
		backgroundColor: "#d9534f", // A reddish color for close/action
		color: "white",
		border: "none",
		borderRadius: "4px",
		fontSize: "14px",
		fontWeight: "bold",
	});

	closeButton.onclick = function () {
		if (overlay.parentNode) {
			overlay.parentNode.removeChild(overlay);
		}
	};

	// Create pre element for the formatted tree (code block)
	const preElement = document.createElement("pre");
	preElement.textContent = formattedTreeString;
	Object.assign(preElement.style, {
		backgroundColor: "#1e1e1e", // Dark background for code block
		color: "#d4d4d4", // Light text color for code
		padding: "15px",
		borderRadius: "5px",
		border: "1px solid #333",
		fontFamily: "monospace",
		whiteSpace: "pre", // Preserve line breaks and spaces from formatted string
		marginTop: "50px", // Space below the absolute positioned button
		overflowX: "auto", // Enable horizontal scroll for very long lines
	});

	// Assemble and append
	overlay.appendChild(closeButton); // Button is a child of overlay
	overlay.appendChild(preElement); // Preformatted tex is a child of overlay
	document.body.appendChild(overlay); // Add overlay to the page
}

function llmPack() {
	window.contentTree = extractPageContentTree();
	window.formattedTree = formatTreeToString(contentTree);
	console.log(location.href, ": ~", formattedTree.length / 4, "tokens");
}

function llmDisplay() {
	// To inspect the tree, you can log it directly or use the new overlay.
	if (contentTree) {
		// Optional: Log the raw JSON tree to console for debugging if needed
		// console.log(JSON.stringify(contentTree, null, 2));

		// Format the tree to a string

		// Display the formatted tree in an overlay
		if (formattedTree) {
			displayTreeOverlay(formattedTree);
		} else {
			console.log(
				"Content tree was generated but resulted in an empty formatted string (e.g. root was pruned or empty).",
			);
		}
	} else {
		console.log(
			"No content tree was extracted (e.g., document.body is not available, or body is empty or contains only filtered elements like scripts/styles).",
		);
	}
}
