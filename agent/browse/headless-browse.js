// Default configuration for DOM processing
const defaultConfig = {
	skippedTags: ["SCRIPT", "NOSCRIPT", "STYLE"], // Tags to skip, in uppercase
	escapeNewlinesInFormat: true, // Default to escape newlines in formatted string output
	showVisibility: false, // Default to show visibility scores in formatted output
	visibilityThreshold: 0.1, // Default visibility threshold for inclusion in formatted output
	urlCropLength: 75, // Default length for URL cropping; <= 0 means infinite
};

function generateUniqueId(generatedIds) {
	const chars = "abcdefghijklmnopqrstuvwxyz0123456789";
	let id;
	do {
		id = "";
		for (let i = 0; i < 3; i++) {
			id += chars.charAt(Math.floor(Math.random() * chars.length));
		}
	} while (generatedIds.has(id));
	generatedIds.add(id);
	return id;
}

// Helper function to process a single element node and its children recursively
function processElementNode(element, config, generatedIds) {
	// Skip elements whose tag names are in the config's skippedTags list
	if (config.skippedTags.includes(element.tagName)) {
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

	// Calculate visibility score
	const computedStyle = window.getComputedStyle(element);
	let visibilityScore = 1.0;

	if (
		computedStyle.display === "none" ||
		computedStyle.visibility === "hidden"
	) {
		visibilityScore = 0.0;
	} else if (computedStyle.opacity !== undefined) {
		const opacityValue = parseFloat(computedStyle.opacity);
		if (!isNaN(opacityValue)) {
			visibilityScore = Math.max(0, Math.min(1, opacityValue)); // Clamp between 0 and 1
		}
	}
	// If an element is determined to be fully invisible by CSS, skip processing its children.
	// This is a heuristic; full invisibility can be complex (e.g. zero size, clipped).
	// For now, display:none or visibility:hidden in computed style are strong indicators.
	// An opacity of 0 also makes it "invisible" in terms of visual impact.
	if (visibilityScore === 0.0) {
		// Although we calculate the score, if it's 0 we might decide not to renderdetailed info.
		// For now, let's proceed and include it in the tree, as it *exists* in DOM.
		// The formatter can later decide what to do with visibilityScore=0 nodes.
		// However, if it's truly display:none, it's reasonable to prune it early.
		// Let's stick to the original pruning logic (by tag or empty content) for now,
		// but attach the score. If the element itself is display:none, its score will be 0.
	}

	const nodeInfo = {
		tagName: element.tagName.toLowerCase(),
		attributes: {},
		visibilityScore: visibilityScore, // Store the calculated visibility score
		domElement: element, // Store reference to the original DOM element
		// Unified list for ordered text nodes and child elements
		childNodesProcessed: [],
		meaningfulReason: null, // Will store why this node is important if not just for text
	};

	// Gather element attributes
	for (const attr of element.attributes) {
		nodeInfo.attributes[attr.name] = attr.value;
	}

	// Check if the element is "meaningful" and set a reason
	const tagNameUpper = element.tagName.toUpperCase();
	const meaningfulTagHandlers = {
		INPUT: (attrs) => {
			const props = [];
			props.push({ key: "type", value: attrs.type || "text" });
			if (attrs.hasOwnProperty("name"))
				props.push({ key: "name", value: attrs.name });
			// Check for value presence, including empty string values
			if (attrs.hasOwnProperty("value"))
				props.push({ key: "value", value: attrs.value });
			if (attrs.hasOwnProperty("placeholder"))
				props.push({ key: "placeholder", value: attrs.placeholder });
			return props;
		},
		TEXTAREA: (attrs) => {
			const props = [];
			if (attrs.hasOwnProperty("name"))
				props.push({ key: "name", value: attrs.name });
			if (attrs.hasOwnProperty("placeholder"))
				props.push({ key: "placeholder", value: attrs.placeholder });
			return props;
		},
		BUTTON: (attrs) => {
			const props = [];
			// Buttons might not always have a name, but their existence is meaningful.
			if (attrs.hasOwnProperty("name"))
				props.push({ key: "name", value: attrs.name });
			return props;
		},
		SELECT: (attrs) => {
			const props = [];
			if (attrs.hasOwnProperty("name"))
				props.push({ key: "name", value: attrs.name });
			return props;
		},
		A: (attrs) => {
			const props = [];
			if (attrs.hasOwnProperty("href"))
				props.push({ key: "href", value: attrs.href });
			return props;
		},
		IMG: (attrs) => {
			const props = [];
			// Order: src, then alt (based on common importance and user example)
			if (attrs.hasOwnProperty("src"))
				props.push({ key: "src", value: attrs.src });
			if (attrs.hasOwnProperty("alt"))
				props.push({ key: "alt", value: attrs.alt }); // alt can be empty string ""
			return props;
		},
		VIDEO: (attrs) => {
			const props = [];
			if (attrs.hasOwnProperty("src"))
				props.push({ key: "src", value: attrs.src });
			return props;
		},
		AUDIO: (attrs) => {
			const props = [];
			if (attrs.hasOwnProperty("src"))
				props.push({ key: "src", value: attrs.src });
			return props;
		},
		LABEL: (attrs) => {
			const props = [];
			if (attrs.hasOwnProperty("for"))
				props.push({ key: "for", value: attrs.for });
			return props;
		},
	};

	if (meaningfulTagHandlers[tagNameUpper]) {
		const props = meaningfulTagHandlers[tagNameUpper](nodeInfo.attributes);
		// Only assign if props array is not empty, to keep meaningfulReason null otherwise.
		// This helps ensure that elements are only considered "meaningful" if they have specific attributes.
		// Correction: An empty props array is fine and means the tag itself (e.g. <button>) is meaningful.
		// Pruning logic `|| nodeInfo.meaningfulReason` (where `nodeInfo.meaningfulReason` is `[]`) is truthy.
		nodeInfo.meaningfulReason = props;
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
			const childElementOutput = processElementNode(
				child,
				config,
				generatedIds,
			); // Pass config recursively
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
		nodeInfo.childNodesProcessed[0].tagName // Ensures it's an element node
	) {
		// The current node (nodeInfo) is a wrapper.
		// Its single child element is nodeInfo.childNodesProcessed[0].
		const childNode = nodeInfo.childNodesProcessed[0];

		// New logic for tagName construction:
		// Avoids redundant prefixes like "div > div > span" if wrapper is "div" and child's tag path starts with "div".
		const wrapperTagName = nodeInfo.tagName; // e.g., "div" (current wrapper's actual tag)
		const childFullTagName = childNode.tagName; // e.g., "div > span" (child's processed tag path) or "span"

		// Extract the first tag from the child's processed tag path.
		// e.g., if childFullTagName is "div > span", childFirstTag is "div".
		// e.g., if childFullTagName is "span", childFirstTag is "span".
		const childFirstTag = childFullTagName.split(" > ")[0];

		if (wrapperTagName !== childFirstTag) {
			// If wrapper is "section" and child is "div > span", result is "section > div > span".
			// If wrapper is "div" and child is "span", result is "div > span".
			childNode.tagName = wrapperTagName + " > " + childFullTagName;
		}
		// Else (wrapperTagName === childFirstTag):
		// If wrapper is "div" and child's tag path is "div > span", the result remains "div > span".
		// childNode.tagName is already childFullTagName, so no change is needed to prepend the wrapper.

		// The childNode also carries over its own attributes and children.
		// Attributes of the wrapper (nodeInfo.attributes) are discarded.
		return childNode; // Return the modified child node in place of the wrapper.
	}

	// Pruning logic (applied if not a collapsed wrapper):
	// Only return the node representation if its childNodesProcessed list is not empty OR it has a meaningfulReason.
	// Empty text nodes and null/empty child elements were already filtered out before being added.
	if (nodeInfo.childNodesProcessed.length > 0 || nodeInfo.meaningfulReason) {
		nodeInfo.id = generateUniqueId(generatedIds);
		return nodeInfo;
	}

	// This element (and its subtree, if no content was found) is considered empty or irrelevant
	return null;
}

// Main function to extract page content as a tree structure
function extractPageContentTree(userConfig = {}) {
	const config = { ...defaultConfig, ...userConfig }; // Merge user config with defaults
	const generatedIds = new Set();

	// Start processing from document.body, as it's the typical container for page content
	if (!document.body) {
		console.warn(
			"document.body is not available. Cannot extract content tree.",
		);
		return null;
	}
	// The root of our content tree will be the processed body element
	return processElementNode(document.body, config, generatedIds);
}

// Helper function to format a node and its children recursively for string output
function formatNodeRecursive(node, indentLevel = 0, config) {
	// If the node's visibility score is below the threshold, skip rendering it and its children.
	if (
		node.hasOwnProperty("visibilityScore") &&
		node.visibilityScore < config.visibilityThreshold
	) {
		return ""; // Exclude this node and its entire branch
	}

	let output = "";
	const indent = "\t".repeat(indentLevel);

	// Build the main line for the current node
	let mainLine = indent + node.tagName;
	output += mainLine + "\n";

	const childIndent = "\t".repeat(indentLevel + 1);

	// Display the generated ID if it exists
	if (node.id) {
		output += childIndent + "id: " + node.id + "\n";
	}

	// If configured, show visibility score
	if (config.showVisibility && node.hasOwnProperty("visibilityScore")) {
		// Format to one decimal place, or more if needed, but avoid excessive precision.
		const visScoreFormatted = parseFloat(node.visibilityScore.toFixed(2));
		output += childIndent + "vis: " + visScoreFormatted + "\n";
	}

	// Display meaningfulReason properties (now an array of {key, value} objects)
	if (
		Array.isArray(node.meaningfulReason) &&
		node.meaningfulReason.length > 0
	) {
		for (const prop of node.meaningfulReason) {
			let displayValue = String(prop.value === null ? "" : prop.value);

			// Apply URL cropping if configured and applicable
			if (
				config.urlCropLength > 0 &&
				(prop.key === "href" || prop.key === "src")
			) {
				let effectiveCropLength = config.urlCropLength;
				if (prop.key === "src" && displayValue.startsWith("data:image")) {
					effectiveCropLength = Math.min(20, config.urlCropLength);
				}

				if (displayValue.length > effectiveCropLength) {
					displayValue = displayValue.substring(0, effectiveCropLength) + "...";
				}
			}

			if (config.escapeNewlinesInFormat) {
				displayValue = displayValue.replace(/\n/g, "\\n");
			}
			output += childIndent + prop.key + ": " + displayValue + "\n";
		}
	}

	// Always iterate through all children (text and elements) to format them.
	// Text nodes are printed as "text: value", and element nodes are recursed.
	for (const child of node.childNodesProcessed) {
		if (child.type === "text") {
			// child.value is already trimmed and checked for emptiness in processElementNode
			let textToDisplay = child.value;
			if (config.escapeNewlinesInFormat) {
				textToDisplay = textToDisplay.replace(/\n/g, "\\n");
			}
			output += childIndent + "text: " + textToDisplay + "\n";
		} else if (child.tagName) {
			// It's an element node
			output += formatNodeRecursive(child, indentLevel + 1, config);
		}
	}
	return output;
}

// Function to format the entire content tree into a string
function formatTreeToString(tree, userFormatConfig = {}) {
	if (!tree) return "";
	// Ensure that defaultConfig (which now contains showVisibility) is used as a base
	const config = { ...defaultConfig, ...userFormatConfig }; // Merge user config with defaults
	return formatNodeRecursive(tree, 0, config); // Start recursion with the root of the tree, pass config
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

function llmPack(userConfig = {}) {
	const configToUse = { ...defaultConfig, ...userConfig };

	window.contentTree = extractPageContentTree(configToUse);
	window.formattedTree = formatTreeToString(window.contentTree, configToUse);
	window.lastUsedConfigForTree = configToUse; // Store the config used for this tree

	// After computing IDs, create a global mapping from ID to DOM element
	window.els = {};
	function populateEls(node) {
		if (!node) {
			return;
		}
		if (node.id && node.domElement) {
			window.els[node.id] = node.domElement;
		}
		if (node.childNodesProcessed) {
			for (const child of node.childNodesProcessed) {
				if (child.tagName) {
					// Recurse on element nodes, skip text nodes
					populateEls(child);
				}
			}
		}
	}
	populateEls(window.contentTree);

	// Ensure formattedTree is used from window scope if it's being assigned to window
	console.log(
		location.href,
		": ~",
		(window.formattedTree || "").length / 4,
		"tokens",
	);
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

let llmVisualizedElements = [];

function llmDisplayVisual(showCloseButton = false) {
	if (typeof document === "undefined" || !document.body) {
		console.warn("DOM environment not available for visual display.");
		return;
	}

	// Remove previous visual elements: clear outlines and remove old button
	if (llmVisualizedElements.length > 0) {
		for (const item of llmVisualizedElements) {
			item.element.style.outline = item.originalOutline;
		}
		llmVisualizedElements = []; // Clear the list
	}

	const existingCloseButton = document.getElementById(
		"dom-visual-close-button",
	);
	if (existingCloseButton) {
		existingCloseButton.parentNode.removeChild(existingCloseButton);
	}

	if (!window.contentTree) {
		console.log("No content tree available to visualize. Run llmPack() first.");
		return;
	}

	const config = window.lastUsedConfigForTree || defaultConfig; // Fallback to defaultConfig

	if (showCloseButton) {
		const closeButton = document.createElement("button");
		closeButton.id = "dom-visual-close-button";
		closeButton.textContent = "Close Visuals";
		Object.assign(closeButton.style, {
			position: "fixed",
			top: "50px", // Positioned to potentially avoid overlap with text overlay's close button
			right: "20px",
			padding: "10px 18px",
			cursor: "pointer",
			backgroundColor: "#5bc0de", // Info blue, distinct from other buttons
			color: "white",
			border: "none",
			borderRadius: "4px",
			fontSize: "14px",
			fontWeight: "bold",
			zIndex: "2147483647", // Max z-index to ensure it's clickable
		});

		closeButton.onclick = function () {
			// Clear outlines
			for (const item of llmVisualizedElements) {
				item.element.style.outline = item.originalOutline;
			}
			llmVisualizedElements = []; // Clear the list

			// Remove the close button itself
			if (closeButton.parentNode) {
				closeButton.parentNode.removeChild(closeButton);
			}
		};
		document.body.appendChild(closeButton);
	}

	function applyOutlinesRecursive(node, currentConfig) {
		if (node && node.domElement && typeof node.visibilityScore === "number") {
			if (node.visibilityScore >= currentConfig.visibilityThreshold) {
				const element = node.domElement;
				const rect = element.getBoundingClientRect();

				// Only apply outline to elements with non-zero dimensions
				if (rect.width > 0 && rect.height > 0) {
					const originalOutline = element.style.outline; // Store current inline outline
					llmVisualizedElements.push({ element, originalOutline });
					element.style.outline = "2px solid red"; // Apply new outline
				}
			}
		}

		if (node && node.childNodesProcessed) {
			for (const child of node.childNodesProcessed) {
				if (child.tagName) {
					// It's an element node (not a text node object)
					applyOutlinesRecursive(child, currentConfig);
				}
			}
		}
	}

	applyOutlinesRecursive(window.contentTree, config);
}
