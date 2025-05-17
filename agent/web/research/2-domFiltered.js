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
		// Unified list for ordered text nodes and child elements
		childNodesProcessed: [],
	};

	// Gather element attributes
	for (const attr of element.attributes) {
		nodeInfo.attributes[attr.name] = attr.value;
	}

	// Process child nodes, preserving order
	for (const child of element.childNodes) {
		if (child.nodeType === Node.TEXT_NODE) {
			const text = child.nodeValue.trim();
			if (text) {
				// Add text node representation
				nodeInfo.childNodesProcessed.push({ type: "text", value: text });
			}
		} else if (child.nodeType === Node.ELEMENT_NODE) {
			const childElementOutput = processElementNode(child);
			if (childElementOutput) {
				// Add processed child element
				nodeInfo.childNodesProcessed.push(childElementOutput);
			}
		}
		// Other node types (comments, etc.) are ignored
	}

	// NEW HEURISTIC: Collapse wrapper elements
	// An element is a "wrapper" if its processed children list contains exactly one item,
	// AND that item is an element node (identifiable by having a tagName property).
	if (
		nodeInfo.childNodesProcessed.length === 1 &&
		nodeInfo.childNodesProcessed[0].tagName
	) {
		// Replace the wrapper with its single child element.
		return nodeInfo.childNodesProcessed[0];
	}

	// Pruning logic (applied if not a collapsed wrapper):
	// Only return the node representation if its childNodesProcessed list is not empty.
	// Empty text nodes and null/empty child elements were already filtered out before being added.
	if (nodeInfo.childNodesProcessed.length > 0) {
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

	// Current node's line: tagName
	output += indent + node.tagName;

	// childNodesProcessed contains an ordered list of text objects and element nodes
	const elementChildren = node.childNodesProcessed.filter((n) => n.tagName); // Element nodes have a tagName
	const textNodeChildren = node.childNodesProcessed.filter(
		(n) => n.type === "text",
	); // Text nodes are {type: "text", value: "..."}

	// If there are ONLY text children (no element children), display text inline with the tag
	if (elementChildren.length === 0 && textNodeChildren.length > 0) {
		const combinedText = textNodeChildren
			.map((t) => t.value)
			.join(" ")
			.trim();
		if (combinedText) {
			// Ensure combined text is not empty after join/trim
			output += ": " + combinedText;
		}
	}
	output += "\n";

	// If there ARE element children, iterate through ALL childNodesProcessed (both text and elements in order).
	// Text nodes are printed as "text: value" on new lines, and element nodes are recursed.
	// This handles mixed content like <span>text1<em>elem</em>text2</span>
	if (elementChildren.length > 0) {
		const childIndent = "\t".repeat(indentLevel + 1);
		for (const child of node.childNodesProcessed) {
			if (child.type === "text") {
				// child.value is already trimmed and checked for emptiness in processElementNode
				output += childIndent + "text: " + child.value + "\n";
			} else if (child.tagName) {
				// It's an element node
				output += formatNodeRecursive(child, indentLevel + 1);
			}
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
