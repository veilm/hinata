// Message input area and generation
import { authFetch } from "./auth.js";
import { renderMarkdown, escapeHtml } from "./markdown.js";
import {
	clearErrorMessages,
	handleError,
	setButtonsDisabledState,
	showToast,
} from "./ui-utils.js";

// To avoid circular dependency, we'll import loadConversationDetails dynamically
let loadConversationDetails;

// Setter for loadConversationDetails to avoid circular dependency
export function setLoadConversationDetails(fn) {
	loadConversationDetails = fn;
}

const ACTIONS = {
	addUser: {
		key: "addUser",
		text: "Add User",
		role: "user",
		styleClass: "btn-add-user",
		gen: false,
	},
	addSystem: {
		key: "addSystem",
		text: "Add System",
		role: "system",
		styleClass: "btn-add-system",
		gen: false,
	},
	addAssistant: {
		key: "addAssistant",
		text: "Add Assistant",
		role: "assistant",
		styleClass: "btn-add-assistant",
		gen: false,
	},
	genAssistant: {
		key: "genAssistant",
		text: "Gen Assistant",
		role: null,
		styleClass: "btn-gen-assistant",
		gen: true,
	},
};

const ACTION_ORDER = [
	ACTIONS.addUser.key,
	ACTIONS.addAssistant.key,
	ACTIONS.addSystem.key,
	ACTIONS.genAssistant.key,
];

const PLUS_ICON =
	'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-plus-icon lucide-plus"><path d="M5 12h14"/><path d="M12 5v14"/></svg>';
const BRAIN_ICON =
	'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-brain-circuit-icon lucide-brain-circuit"><path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M9 13a4.5 4.5 0 0 0 3-4"/><path d="M6.003 5.125A3 3 0 0 0 6.401 6.5"/><path d="M3.477 10.896a4 4 0 0 1 .585-.396"/><path d="M6 18a4 4 0 0 1-1.967-.516"/><path d="M12 13h4"/><path d="M12 18h6a2 2 0 0 1 2 2v1"/><path d="M12 8h8"/><path d="M16 8V5a2 2 0 0 1 2-2"/><circle cx="16" cy="13" r=".5"/><circle cx="18" cy="3" r=".5"/><circle cx="20" cy="21" r=".5"/><circle cx="20" cy="8" r=".5"/></svg>';
const LOADING_SPINNER_ICON =
	'<span class="button-spinner" aria-hidden="true"></span>';

let selectedActionKey = null;
let manualModeSelection = false;
let lastRecommendedActionKey = null;
const COMPOSER_PADDING_BUFFER = 40;
let composerResizeObserver = null;
let windowResizeListenerAttached = false;

function updateBodyPaddingForComposer() {
	const messageInputArea = document.getElementById("message-input-area");
	if (!messageInputArea) {
		document.body.style.paddingBottom = "";
		return;
	}
	const composerHeight = messageInputArea.offsetHeight || 0;
	const paddingValue = Math.max(0, composerHeight) + COMPOSER_PADDING_BUFFER;
	document.body.style.paddingBottom = `${paddingValue}px`;
}

function observeComposerForPadding(target) {
	if (typeof ResizeObserver !== "undefined") {
		if (composerResizeObserver) {
			composerResizeObserver.disconnect();
		}
		composerResizeObserver = new ResizeObserver(() => {
			updateBodyPaddingForComposer();
		});
		composerResizeObserver.observe(target);
	} else if (!windowResizeListenerAttached) {
		window.addEventListener("resize", updateBodyPaddingForComposer);
		windowResizeListenerAttached = true;
	}
}

function disconnectComposerObserver() {
	if (composerResizeObserver) {
		composerResizeObserver.disconnect();
		composerResizeObserver = null;
	}
}

function setupMessageInputArea(conversationId) {
	let messageInputArea = document.getElementById("message-input-area");

	// Clear previous input area if any (e.g., on reload/re-render)
	if (messageInputArea) {
		messageInputArea.remove();
	}
	disconnectComposerObserver();

	messageInputArea = document.createElement("div");
	messageInputArea.id = "message-input-area";
	manualModeSelection = false;
	selectedActionKey = null;
	lastRecommendedActionKey = null;

	const textarea = document.createElement("textarea");
	textarea.id = "new-message-content";
	textarea.placeholder = "Enter message content...";
	textarea.rows = 1; // Start with a single line; JS will grow it dynamically
	textarea.style.overflowY = "hidden"; // Start with hidden scrollbar, JS will manage
	textarea.style.resize = "none"; // Prevent manual resize conflicting with auto-resize

	const storageKey = `hinata-draft-${conversationId}`;
	const savedContent = localStorage.getItem(storageKey);
	if (savedContent) {
		textarea.value = savedContent;
	}

	let lastSavedContent = savedContent || "";
	setInterval(() => {
		if (textarea.value !== lastSavedContent) {
			localStorage.setItem(storageKey, textarea.value);
			lastSavedContent = textarea.value;
		}
	}, 2000);

	// Function to adjust textarea height dynamically
	function adjustTextareaHeightOnInput(ta) {
		const computedStyle = getComputedStyle(ta);
		const fontSize = parseFloat(computedStyle.fontSize) || 16; // Base font size from computed style or fallback
		// Ensure lineHeight is a number. If 'normal', approximate as 1.2 * fontSize.
		const lineHeight =
			computedStyle.lineHeight === "normal"
				? fontSize * 1.2
				: parseFloat(computedStyle.lineHeight);

		const paddingTop = parseFloat(computedStyle.paddingTop);
		const paddingBottom = parseFloat(computedStyle.paddingBottom);
		const borderTopWidth = parseFloat(computedStyle.borderTopWidth);
		const borderBottomWidth = parseFloat(computedStyle.borderBottomWidth);

		const M_MAX_LINES = 8;

		// Calculate max content height based on M_MAX_LINES
		const maxContentHeight = M_MAX_LINES * lineHeight;
		// Calculate max border-box height (since box-sizing: border-box is used)
		const maxBorderBoxHeight =
			maxContentHeight +
			paddingTop +
			paddingBottom +
			borderTopWidth +
			borderBottomWidth;

		// Temporarily reset height to 'auto'. This allows scrollHeight to accurately report the full content height.
		// The CSS min-height will ensure it doesn't visually collapse too much during this brief phase.
		ta.style.height = "auto";

		// scrollHeight includes content height + padding height.
		const currentScrollHeight = ta.scrollHeight;

		// Calculate the desired border-box height based on current content.
		// This includes the content, padding (already in scrollHeight), and border.
		const desiredBorderBoxHeight =
			currentScrollHeight + borderTopWidth + borderBottomWidth;

		if (desiredBorderBoxHeight > maxBorderBoxHeight) {
			ta.style.height = maxBorderBoxHeight + "px";
			ta.style.overflowY = "auto"; // Show scrollbar as content exceeds max height
		} else {
			// Set height to what content needs (as border-box).
			// If desiredBorderBoxHeight is less than CSS min-height, CSS min-height takes precedence.
			ta.style.height = desiredBorderBoxHeight + "px";
			ta.style.overflowY = "hidden"; // Hide scrollbar if content fits
		}

		updateBodyPaddingForComposer();
	}

	textarea.addEventListener("input", () => {
		adjustTextareaHeightOnInput(textarea);
		updateSplitButtonState(conversationId);
		// Save draft to localStorage
		const storageKey = `hinata-draft-${conversationId}`;
		if (textarea.value.trim()) {
			localStorage.setItem(storageKey, textarea.value);
		} else {
			localStorage.removeItem(storageKey);
		}
	});
	// Initial call to set height will be done after textarea is appended to DOM.

	const composer = document.createElement("div");
	composer.className = "message-composer";

	const buttonsDiv = document.createElement("div");
	buttonsDiv.id = "message-buttons";
	buttonsDiv.classList.add("message-input-controls");

	const modeSelector = document.createElement("div");
	modeSelector.className = "mode-selector";

	const dropdownToggleBtn = document.createElement("button");
	dropdownToggleBtn.id = "dropdown-toggle-btn";
	dropdownToggleBtn.type = "button";
	dropdownToggleBtn.classList.add("mode-toggle-btn");

	const modeLabel = document.createElement("span");
	modeLabel.className = "mode-toggle-label";
	modeLabel.textContent = "Select action";
	dropdownToggleBtn.appendChild(modeLabel);

	const caretSpan = document.createElement("span");
	caretSpan.className = "mode-toggle-caret";
	caretSpan.innerHTML =
		'<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-chevron-up-down-icon lucide-chevron-up-down"><path d="m7 15 5 5 5-5"/><path d="m7 9 5-5 5 5"/></svg>';
	dropdownToggleBtn.appendChild(caretSpan);

	const dropdownMenu = document.createElement("div");
	dropdownMenu.id = "action-dropdown-menu";
	dropdownMenu.classList.add("hidden");

	dropdownToggleBtn.addEventListener("click", () => {
		dropdownMenu.classList.toggle("hidden");
	});

	modeSelector.appendChild(dropdownToggleBtn);
	modeSelector.appendChild(dropdownMenu);

	const primaryBtn = document.createElement("button");
	primaryBtn.id = "primary-action-btn";
	primaryBtn.type = "button";
	primaryBtn.classList.add("message-submit-btn");

	buttonsDiv.appendChild(modeSelector);
	buttonsDiv.appendChild(primaryBtn);

	composer.appendChild(textarea);
	composer.appendChild(buttonsDiv);

	messageInputArea.appendChild(composer);

	// Append the whole message input area directly to the body for fixed positioning
	document.body.appendChild(messageInputArea);
	adjustTextareaHeightOnInput(textarea); // Initial height adjustment
	observeComposerForPadding(messageInputArea);
}
function updateSplitButtonState(conversationId) {
	const primaryBtn = document.getElementById("primary-action-btn");
	const dropdownToggleBtn = document.getElementById("dropdown-toggle-btn");
	const dropdownMenu = document.getElementById("action-dropdown-menu");
	const textarea = document.getElementById("new-message-content");
	if (!primaryBtn || !dropdownToggleBtn || !dropdownMenu || !textarea) return;

	const allButtons = [primaryBtn, dropdownToggleBtn];

	const messages = document.querySelectorAll(
		"#messages-container .message:not(.archived-message)",
	);
	const lastMessage =
		messages.length > 0 ? messages[messages.length - 1] : null;
	const lastMessageIsUser =
		lastMessage && lastMessage.classList.contains("message-user");

	const hasTextareaContent = textarea.value.trim().length > 0;

	let recommendedActionKey;

	if (lastMessageIsUser) {
		recommendedActionKey = hasTextareaContent
			? ACTIONS.addAssistant.key
			: ACTIONS.genAssistant.key;
	} else {
		recommendedActionKey = ACTIONS.addUser.key;
	}

	lastRecommendedActionKey = recommendedActionKey;

	if (
		!manualModeSelection ||
		!selectedActionKey ||
		!ACTIONS[selectedActionKey]
	) {
		selectedActionKey = recommendedActionKey;
	}

	const selectedAction = ACTIONS[selectedActionKey] || ACTIONS.addUser;

	primaryBtn.className = `message-submit-btn ${selectedAction.styleClass}`;
	primaryBtn.innerHTML = selectedAction.gen ? BRAIN_ICON : PLUS_ICON;
	primaryBtn.setAttribute("aria-label", selectedAction.text);
	primaryBtn.setAttribute("title", selectedAction.text);

	const modeLabel =
		dropdownToggleBtn.querySelector(".mode-toggle-label") ||
		dropdownToggleBtn;
	modeLabel.textContent = selectedAction.text;
	dropdownToggleBtn.setAttribute("aria-label", `Mode: ${selectedAction.text}`);

	if (primaryBtn.clickHandler) {
		primaryBtn.removeEventListener("click", primaryBtn.clickHandler);
	}
	const submitHandler = () => {
		if (selectedAction.gen) {
			handleGenAssistant(conversationId, allButtons);
		} else {
			handleAddMessage(
				conversationId,
				selectedAction.role,
				textarea,
				allButtons,
			);
		}
	};
	primaryBtn.clickHandler = submitHandler;
	primaryBtn.addEventListener("click", submitHandler);

	dropdownMenu.innerHTML = "";
	ACTION_ORDER.forEach((actionKey) => {
		const action = ACTIONS[actionKey];
		if (!action) {
			return;
		}
		const button = document.createElement("button");
		button.type = "button";
		button.textContent = action.text;
		if (action.key === selectedAction.key) {
			button.classList.add("selected");
		}
		button.addEventListener("click", () => {
			selectedActionKey = action.key;
			manualModeSelection = action.key !== lastRecommendedActionKey;
			dropdownMenu.classList.add("hidden");
			updateSplitButtonState(conversationId);
		});
		dropdownMenu.appendChild(button);
		allButtons.push(button);
	});
}
async function handleAddMessage(
	conversationId,
	role,
	textareaElement,
	allButtons,
) {
	const content = textareaElement.value; // Keep original content with leading/trailing spaces if user entered them
	// No client-side check for empty content, backend/hnt-chat handles it.

	setButtonsDisabledState(allButtons, true);
	clearErrorMessages(document.getElementById("message-input-area"));

	try {
		const response = await authFetch(
			`/api/conversation/${encodeURIComponent(conversationId)}/add-message`,
			{
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ role: role, content: content }),
			},
		);

		if (!response.ok) {
			const errorData = await response
				.json()
				.catch(() => ({ detail: "Failed to add message." }));
			throw new Error(errorData.detail || `HTTP error ${response.status}`);
		}

		const storageKey = `hinata-draft-${conversationId}`;
		localStorage.removeItem(storageKey);

		textareaElement.value = ""; // Clear textarea on success

		// Show success toast
		const roleDisplay = role.charAt(0).toUpperCase() + role.slice(1);
		showToast(`${roleDisplay} message added`, "success");

		loadConversationDetails(conversationId); // Reload to show new message
	} catch (error) {
		console.error(`Error adding ${role} message:`, error);
		handleError(
			`Error adding ${role} message: ${error.message}`,
			document.getElementById("message-input-area"),
		);
		setButtonsDisabledState(allButtons, false); // Re-enable buttons on error if not reloading
	}
	// No 'finally' block to re-enable buttons because loadConversationDetails will recreate them.
	// If loadConversationDetails failed or an error occurred before it, buttons are re-enabled in catch.
}
async function handleGenAssistant(conversationId, allButtons) {
	setButtonsDisabledState(allButtons, true);
	const messageInputArea = document.getElementById("message-input-area");
	if (messageInputArea) {
		clearErrorMessages(messageInputArea);
	}

	const primaryBtn = document.getElementById("primary-action-btn");
	if (primaryBtn) {
		primaryBtn.classList.add("is-loading");
		primaryBtn.setAttribute("aria-label", "Generating response");
		primaryBtn.innerHTML = LOADING_SPINNER_ICON;
	}

	// Remove any existing placeholder
	const existingPlaceholder = document.getElementById(
		"assistant-streaming-placeholder",
	);
	if (existingPlaceholder) {
		existingPlaceholder.remove();
	}

	// Create a new placeholder div for the streaming assistant message
	const messagesContainer = document.getElementById("messages-container");
	const placeholderDiv = document.createElement("div");
	placeholderDiv.id = "assistant-streaming-placeholder";
	placeholderDiv.className = "message message-assistant";

	const contentWrapperDiv = document.createElement("div");
	contentWrapperDiv.className = "message-content-wrapper";
	contentWrapperDiv.style.whiteSpace = "pre-wrap"; // Ensure pre-wrap for streaming

	// Create reasoning container (will be populated if reasoning content arrives)
	let reasoningContainer = null;
	let reasoningContent = null;
	let reasoningHeader = null;
	let toggleIcon = null;

	// Reasoning container will be inserted here when needed
	placeholderDiv.appendChild(contentWrapperDiv);

	// Insert before archive section if it exists, otherwise append to end
	const archiveDivider = messagesContainer.querySelector(".archive-divider");
	if (archiveDivider) {
		messagesContainer.insertBefore(placeholderDiv, archiveDivider);
	} else {
		messagesContainer.appendChild(placeholderDiv);
	}
	// Removed: placeholderDiv.scrollIntoView({ behavior: "smooth", block: "end" });

	try {
		const response = await authFetch(
			`/api/conversation/${encodeURIComponent(conversationId)}/gen-assistant`,
			{
				method: "POST",
			},
		);

		if (!response.ok) {
			// This handles errors sent *before* the stream starts (e.g., server 500)
			const errorData = await response.json().catch(() => ({
				detail: `Failed to start assistant message generation. Server responded with ${response.status}.`,
			}));
			throw new Error(errorData.detail || `HTTP error ${response.status}`);
		}

		// Handle the stream
		const reader = response.body.getReader();
		const decoder = new TextDecoder(); // Defaults to 'utf-8'

		let done = false;
		let buffer = "";
		let hasReasoning = false;
		while (!done) {
			const { value, done: readerDone } = await reader.read();
			done = readerDone;
			if (value) {
				const chunk = decoder.decode(value, { stream: !done });
				buffer += chunk;

				// Process SSE format if present
				const lines = buffer.split("\n");
				buffer = lines.pop() || ""; // Keep the last incomplete line in buffer

				for (const line of lines) {
					if (line.startsWith("data: ")) {
						const data = line.slice(6); // Remove 'data: ' prefix
						// Skip the [DONE] token that signals end of stream
						if (data.trim() && data.trim() !== "[DONE]") {
							// Check if this is reasoning content
							if (data.startsWith("[REASONING]")) {
								// Remove [REASONING] prefix and unescape newlines
								const reasoningText = data.slice(11).replace(/\\n/g, "\n");
								if (!hasReasoning) {
									hasReasoning = true;
									// Create collapsible reasoning section
									reasoningContainer = document.createElement("div");
									reasoningContainer.className = "message-reasoning-container";
									reasoningContainer.style.margin = "0 0 10px 0";

									reasoningHeader = document.createElement("div");
									reasoningHeader.className = "reasoning-header";
									reasoningHeader.style.cursor = "pointer";
									reasoningHeader.style.backgroundColor = "#0a0a0a";
									reasoningHeader.style.padding = "8px 12px";
									reasoningHeader.style.borderRadius = "5px";
									reasoningHeader.style.display = "flex";
									reasoningHeader.style.alignItems = "center";
									reasoningHeader.style.justifyContent = "space-between";
									reasoningHeader.style.userSelect = "none";

									const reasoningLabel = document.createElement("span");
									reasoningLabel.style.fontWeight = "bold";
									reasoningLabel.style.color = "#6ec8ff";
									reasoningLabel.textContent = "Reasoning";

									toggleIcon = document.createElement("span");
									toggleIcon.style.fontSize = "12px";
									toggleIcon.style.color = "#4a8ab7";
									toggleIcon.textContent = "▶"; // Right arrow when collapsed

									reasoningHeader.appendChild(reasoningLabel);
									reasoningHeader.appendChild(toggleIcon);

									reasoningContent = document.createElement("div");
									reasoningContent.className = "message-reasoning";
									reasoningContent.style.backgroundColor = "#050505";
									reasoningContent.style.padding = "12px";
									reasoningContent.style.marginTop = "4px";
									reasoningContent.style.borderRadius = "5px";
									reasoningContent.style.color = "#a0a0a0";
									reasoningContent.style.display = "none"; // Hidden by default
									reasoningContent.style.whiteSpace = "pre-wrap";

									// Toggle handler
									reasoningHeader.addEventListener("click", () => {
										const isVisible = reasoningContent.style.display !== "none";
										reasoningContent.style.display = isVisible
											? "none"
											: "block";
										toggleIcon.textContent = isVisible ? "▶" : "▼";
									});

									reasoningContainer.appendChild(reasoningHeader);
									reasoningContainer.appendChild(reasoningContent);

									// Insert before content wrapper
									placeholderDiv.insertBefore(
										reasoningContainer,
										contentWrapperDiv,
									);
								}
								// Append text while preserving newlines
								if (!reasoningContent.dataset.rawText) {
									reasoningContent.dataset.rawText = reasoningText;
									reasoningContent.innerHTML = renderMarkdown(reasoningText);
								} else {
									// For streaming, append to existing text and re-render
									reasoningContent.dataset.rawText += reasoningText;
									reasoningContent.innerHTML = renderMarkdown(
										reasoningContent.dataset.rawText,
									);
								}
							} else {
								// Unescape newlines in regular content
								const unescapedData = data.replace(/\\n/g, "\n");
								if (!contentWrapperDiv.dataset.rawText) {
									contentWrapperDiv.dataset.rawText = unescapedData;
								} else {
									contentWrapperDiv.dataset.rawText += unescapedData;
								}
								contentWrapperDiv.innerHTML = renderMarkdown(
									contentWrapperDiv.dataset.rawText,
								);
							}
						}
					} else if (line.trim() && !line.startsWith(":")) {
						// If it's not SSE format, just append the line
						contentWrapperDiv.textContent += line;
					}
				}
				// Removed: placeholderDiv.scrollIntoView({ block: "end" });
			}
		}
		// Process any remaining data in buffer
		if (buffer.trim()) {
			if (buffer.startsWith("data: ")) {
				const data = buffer.slice(6);
				// Skip the [DONE] token
				if (data.trim() !== "[DONE]") {
					if (data.startsWith("[REASONING]")) {
						const reasoningText = data.slice(11);
						if (!hasReasoning) {
							hasReasoning = true;
							// Create collapsible reasoning section (same as above)
							reasoningContainer = document.createElement("div");
							reasoningContainer.className = "message-reasoning-container";
							reasoningContainer.style.margin = "0 0 10px 0";

							reasoningHeader = document.createElement("div");
							reasoningHeader.className = "reasoning-header";
							reasoningHeader.style.cursor = "pointer";
							reasoningHeader.style.backgroundColor = "#0a0a0a";
							reasoningHeader.style.padding = "8px 12px";
							reasoningHeader.style.borderRadius = "5px";
							reasoningHeader.style.display = "flex";
							reasoningHeader.style.alignItems = "center";
							reasoningHeader.style.justifyContent = "space-between";
							reasoningHeader.style.userSelect = "none";

							const reasoningLabel = document.createElement("span");
							reasoningLabel.style.fontWeight = "bold";
							reasoningLabel.style.color = "#6ec8ff";
							reasoningLabel.textContent = "Reasoning";

							toggleIcon = document.createElement("span");
							toggleIcon.style.fontSize = "12px";
							toggleIcon.style.color = "#4a8ab7";
							toggleIcon.textContent = "▶"; // Right arrow when collapsed

							reasoningHeader.appendChild(reasoningLabel);
							reasoningHeader.appendChild(toggleIcon);

							reasoningContent = document.createElement("div");
							reasoningContent.className = "message-reasoning";
							reasoningContent.style.backgroundColor = "#050505";
							reasoningContent.style.padding = "12px";
							reasoningContent.style.marginTop = "4px";
							reasoningContent.style.borderRadius = "5px";
							reasoningContent.style.color = "#a0a0a0";
							reasoningContent.style.display = "none"; // Hidden by default
							reasoningContent.style.whiteSpace = "pre-wrap";

							// Toggle handler
							reasoningHeader.addEventListener("click", () => {
								const isVisible = reasoningContent.style.display !== "none";
								reasoningContent.style.display = isVisible ? "none" : "block";
								toggleIcon.textContent = isVisible ? "▶" : "▼";
							});

							reasoningContainer.appendChild(reasoningHeader);
							reasoningContainer.appendChild(reasoningContent);

							// Insert before content wrapper
							placeholderDiv.insertBefore(
								reasoningContainer,
								contentWrapperDiv,
							);
						}
						// For streaming, append to existing text and re-render
						if (!reasoningContent.dataset.rawText) {
							reasoningContent.dataset.rawText = reasoningText;
						} else {
							reasoningContent.dataset.rawText += reasoningText;
						}
						reasoningContent.innerHTML = renderMarkdown(
							reasoningContent.dataset.rawText,
						);
					} else {
						// Unescape newlines in regular content
						const unescapedData = data.replace(/\\n/g, "\n");
						contentWrapperDiv.textContent += unescapedData;
					}
				}
			} else {
				// Unescape newlines in regular content
				const unescapedBuffer = buffer.replace(/\\n/g, "\n");
				contentWrapperDiv.textContent += unescapedBuffer;
			}
		}
		// Stream finished
	} catch (error) {
		console.error("Error generating assistant message:", error);
		if (messageInputArea) {
			handleError(
				`Error generating assistant message: ${error.message}`,
				messageInputArea,
			);
		}
		// Update placeholder to show error if stream itself failed or setup failed.
		contentWrapperDiv.textContent =
			"Error during generation: " + escapeHtml(error.message);
		// Do not re-enable buttons here, `finally` block below calls loadConversationDetails
		// which will fully reconstruct the input area.
		// If loadConversationDetails is skipped on error, then buttons should be re-enabled.
		// However, the design is to always try to load details.
	} finally {
		// Regardless of success or failure of the stream, reload the conversation details
		// to get the final state from the server (new messages, files, etc.)
		// This will also remove the placeholder and re-enable buttons correctly.
		// Pass false to prevent auto-scrolling after LLM generation completes
		loadConversationDetails(conversationId, false);
	}
}

export {
	setupMessageInputArea,
	updateSplitButtonState,
	handleAddMessage,
	handleGenAssistant,
};
