// Conversation management - load, create, fork, pin
import { authFetch } from "./auth.js";
import { renderMarkdown, escapeHtml } from "./markdown.js";
import {
	showToast,
	clearErrorMessages,
	handleError,
	createActionButton,
	setButtonsDisabledState,
	jumpToLatestMessage,
	showMessageInfoModal,
	updateGlobalActionButtonsState,
} from "./ui-utils.js";
import {
	DEFAULT_MODEL_NAME,
	ICON_PIN,
	ICON_INFO,
	ICON_PENCIL,
	ICON_SPLIT,
	ICON_ARCHIVE,
	ICON_COPY,
} from "./constants.js";
import {
	toggleEditState,
	handleArchiveMessage,
	handleCopyMessage,
	toggleForkEditState,
} from "./message-actions.js";
import {
	setupMessageInputArea,
	updateSplitButtonState,
	setLoadConversationDetails,
} from "./message-input.js";
import { showShareModal } from "./share.js";

async function loadConversationsList() {
	const container = document.getElementById("conversation-list-container");
	try {
		const response = await authFetch("/api/conversations");
		if (!response.ok) {
			throw new Error(`HTTP error! status: ${response.status}`);
		}
		const data = await response.json(); // Expects { conversations: [{id: "...", title: "...", is_pinned: bool}, ...] }

		if (data.conversations && data.conversations.length > 0) {
			// Group conversations by fork relationships
			const rootConversations = [];
			const forkMap = new Map(); // root ID -> list of fork conversations
			const allConvsMap = new Map(); // ID -> conversation object

			// First pass: build maps
			data.conversations.forEach((conv) => {
				allConvsMap.set(conv.id, conv);

				if (!conv.fork_source) {
					// This is a root conversation
					rootConversations.push(conv);
					if (!forkMap.has(conv.id)) {
						forkMap.set(conv.id, []);
					}
				}
			});

			// Second pass: populate fork map
			data.conversations.forEach((conv) => {
				if (conv.fork_source) {
					// This is a fork
					if (!forkMap.has(conv.fork_source)) {
						forkMap.set(conv.fork_source, []);
					}
					forkMap.get(conv.fork_source).push(conv);
				}
			});

			// Helper function to create conversation list item
			const createConversationItem = (conv, isRoot = true) => {
				const li = document.createElement("li");
				li.style.display = "flex";
				li.style.alignItems = "center";
				li.style.gap = "15px";

				if (conv.is_pinned) {
					li.classList.add("pinned-conversation");
				}
				if (!isRoot) {
					li.style.marginLeft = "40px"; // Indent forks
					li.style.fontSize = "0.95em"; // Slightly smaller font for forks
					li.classList.add("fork-conversation");
				}

				// Convert nanosecond timestamp to date
				const timestampNs = parseInt(conv.id);
				const timestampMs = Math.floor(timestampNs / 1000000); // Convert ns to ms
				const date = new Date(timestampMs);
				const dateStr = date.toLocaleDateString("en-US", {
					month: "short",
					day: "2-digit",
					year: "numeric",
				});

				// Date span (not clickable)
				const dateSpan = document.createElement("span");
				dateSpan.style.color = "#e0e0e0";
				dateSpan.style.minWidth = "100px";
				if (!isRoot) {
					dateSpan.style.marginLeft = "10px";
				}
				dateSpan.textContent = dateStr;
				li.appendChild(dateSpan);

				// Title link
				const a = document.createElement("a");
				a.href = `/c/${encodeURIComponent(conv.id)}`;
				let displayTitle = escapeHtml(conv.title).trim();
				if (!displayTitle || displayTitle === "-") {
					displayTitle = "Untitled";
				}
				a.textContent = displayTitle;
				li.appendChild(a);

				// Pin icon (if pinned)
				if (conv.is_pinned) {
					const pinSpan = document.createElement("span");
					pinSpan.className = "pin-emoji";
					pinSpan.innerHTML = ICON_PIN;
					li.appendChild(pinSpan);
				}

				return li;
			};

			const ul = document.createElement("ul");

			// Display root conversations with their forks
			rootConversations.forEach((rootConv) => {
				// Add root conversation
				ul.appendChild(createConversationItem(rootConv, true));

				// Add its forks (if any)
				const forks = forkMap.get(rootConv.id) || [];

				// Sort forks by their order in the root's forks.txt
				if (rootConv.forks && rootConv.forks.length > 0) {
					// Use the order from forks.txt
					rootConv.forks.forEach((forkId) => {
						const forkConv = forks.find((f) => f.id === forkId);
						if (forkConv) {
							ul.appendChild(createConversationItem(forkConv, false));
						}
					});
				} else {
					// Fallback: just add any forks we found
					forks.forEach((forkConv) => {
						ul.appendChild(createConversationItem(forkConv, false));
					});
				}
			});

			container.innerHTML = ""; // Clear "Loading..."
			container.appendChild(ul);
		} else {
			container.innerHTML = "<p>No conversations found.</p>";
		}
	} catch (error) {
		handleError("Failed to load conversations.", container);
		console.error("Error loading conversations:", error);
	}
}
async function handleCreateConversation() {
	const button = document.getElementById("create-conversation-btn");
	if (button) {
		button.disabled = true;
	}

	const buttonContainer = button ? button.parentElement : null;
	if (buttonContainer) {
		clearErrorMessages(buttonContainer); // Clear previous errors from this section
	}

	try {
		const response = await authFetch("/api/conversations/create", {
			method: "POST",
			headers: {
				"Content-Type": "application/json", // Though not sending a body, good practice
			},
		});

		if (!response.ok) {
			let errorDetail = "Failed to create conversation.";
			try {
				const errorData = await response.json();
				if (errorData && errorData.detail) {
					errorDetail = errorData.detail;
				}
			} catch (e) {
				// If response is not JSON or other parsing error
				errorDetail += ` Server responded with: ${response.status} ${response.statusText}`;
			}
			throw new Error(errorDetail);
		}

		const responseData = await response.json();
		if (responseData && responseData.conversation_id) {
			// Success! Navigate to the new conversation page.
			window.location.href = `/c/${encodeURIComponent(responseData.conversation_id)}`;
		} else {
			// Fallback if conversation_id is not in response, though backend should ensure it
			throw new Error(
				"Conversation created, but ID was not returned. Reloading list.",
			);
		}
	} catch (error) {
		console.error("Error creating conversation:", error);
		// If navigation fails or ID is missing, reload the list page as a fallback.
		// This part of the catch block handles the custom error thrown above or other fetch errors.
		if (
			error.message ===
			"Conversation created, but ID was not returned. Reloading list."
		) {
			window.location.reload(); // Reload to show it in the list at least
		}
		// Display error message near the button or in a general area
		handleError(
			error.message,
			buttonContainer || document.getElementById("conversation-list-container"),
		);
		if (button) {
			button.disabled = false; // Re-enable button on error
		}
	}
}
async function loadConversationDetails(conversationId) {
	const mainTitleDisplayElement = document.getElementById(
		"conversation-id-display",
	);
	// Settings modal elements
	const settingsModal = document.getElementById("settings-modal");
	const settingsToggleBtn = document.getElementById("settings-toggle-btn");
	const settingsCloseBtn = document.getElementById("settings-modal-close");
	const modalTitleInput = document.getElementById("modal-title-input");
	const modalModelInput = document.getElementById("modal-model-input");
	const modalPinToggleBtn = document.getElementById("modal-pin-toggle-btn");
	const modalPinText = document.getElementById("modal-pin-text");
	const modalForkBtn = document.getElementById("modal-fork-btn");
	const modalShareBtn = document.getElementById("modal-share-btn");
	const messagesContainer = document.getElementById("messages-container");
	const otherFilesContainer = document.getElementById("other-files-container");

	const safeConvId = escapeHtml(conversationId);

	// Initial state for inputs and buttons
	document.title = `Loading conversation...`;
	mainTitleDisplayElement.textContent = `Loading conversation...`;
	if (modalTitleInput) {
		modalTitleInput.value = "";
		modalTitleInput.disabled = true;
	}
	if (modalModelInput) {
		modalModelInput.value = "";
		modalModelInput.disabled = true;
	}
	if (modalPinToggleBtn) {
		modalPinToggleBtn.disabled = true;
		if (modalPinText) modalPinText.textContent = "Pin Conversation"; // Default before loading
	}

	try {
		const response = await authFetch(
			`/api/conversation/${encodeURIComponent(conversationId)}`,
		);
		if (!response.ok) {
			throw new Error(`HTTP error! status: ${response.status}`);
		}
		const data = await response.json(); // Expects { ..., title, model, is_pinned, messages, ... }

		// --- Title Handling ---
		const convTitle = data.title || "-";
		const updateDisplayedTitle = (currentTitle, isPinned = false) => {
			const displayPageTitle =
				currentTitle && currentTitle !== "-"
					? escapeHtml(currentTitle)
					: `Conversation ${safeConvId}`;
			document.title = displayPageTitle;

			// Clear the h1 and rebuild with pin icon if needed
			mainTitleDisplayElement.innerHTML = "";

			if (isPinned) {
				// Add pin icon
				const pinIcon = document.createElement("span");
				pinIcon.className = "title-pin-icon";
				pinIcon.style.display = "inline-block";
				pinIcon.style.marginRight = "8px";
				pinIcon.style.verticalAlign = "middle";
				pinIcon.innerHTML = ICON_PIN.replace(
					'width="24"',
					'width="20"',
				).replace('height="24"', 'height="20"');
				mainTitleDisplayElement.appendChild(pinIcon);
			}

			// Add title text
			const titleSpan = document.createElement("span");
			titleSpan.textContent = displayPageTitle;
			mainTitleDisplayElement.appendChild(titleSpan);
		};
		updateDisplayedTitle(convTitle, data.is_pinned);

		if (modalTitleInput) {
			modalTitleInput.value = escapeHtml(convTitle === "-" ? "" : convTitle);
			modalTitleInput.dataset.originalTitle = convTitle;
			modalTitleInput.disabled = false;

			modalTitleInput.addEventListener("blur", async () => {
				let newTitleAttempt = modalTitleInput.value.trim();
				const originalTitle = modalTitleInput.dataset.originalTitle;

				if (newTitleAttempt === "") {
					newTitleAttempt = "-"; // Default to "-" if input is cleared
				}

				if (newTitleAttempt !== originalTitle) {
					try {
						await updateConversationTitle(
							conversationId,
							newTitleAttempt,
							modalTitleInput,
						);
						// updateConversationTitle handles updating dataset.originalTitle and input value on success
						updateDisplayedTitle(
							modalTitleInput.dataset.originalTitle,
							data.is_pinned,
						); // Update H1 and document title
					} catch (error) {
						modalTitleInput.value = escapeHtml(
							originalTitle === "-" ? "" : originalTitle,
						);
					}
				} else {
					modalTitleInput.value = escapeHtml(
						originalTitle === "-" ? "" : originalTitle,
					);
				}
			});
			modalTitleInput.addEventListener("keypress", (event) => {
				if (event.key === "Enter") modalTitleInput.blur();
			});
		}

		// --- Model Handling ---
		const convModel = data.model || DEFAULT_MODEL_NAME; // Backend ensures default if missing/empty
		if (modalModelInput) {
			modalModelInput.value = escapeHtml(convModel);
			modalModelInput.dataset.originalModel = convModel;
			modalModelInput.disabled = false;

			modalModelInput.addEventListener("blur", async () => {
				let newModelAttempt = modalModelInput.value.trim(); // Can be empty
				const originalModel = modalModelInput.dataset.originalModel;

				if (newModelAttempt !== originalModel) {
					try {
						await updateConversationModel(
							conversationId,
							newModelAttempt,
							modalModelInput,
						);
						// updateConversationModel handles updating dataset.originalModel and input value
					} catch (error) {
						modalModelInput.value = escapeHtml(originalModel);
					}
				} else {
					// Ensure field shows the clean originalModel if user just added/removed spaces
					modalModelInput.value = escapeHtml(originalModel);
				}
			});
			modalModelInput.addEventListener("keypress", (event) => {
				if (event.key === "Enter") modalModelInput.blur();
			});
		}

		// --- Pin/Unpin Button Setup in Modal ---
		if (modalPinToggleBtn) {
			if (modalPinText) {
				modalPinText.textContent = data.is_pinned
					? "Unpin Conversation"
					: "Pin Conversation";
			}
			modalPinToggleBtn.disabled = false;
			const newPinButton = modalPinToggleBtn.cloneNode(true); // Clone to remove old listeners
			modalPinToggleBtn.parentNode.replaceChild(
				newPinButton,
				modalPinToggleBtn,
			);
			newPinButton.addEventListener("click", async () => {
				await handlePinToggle(conversationId, newPinButton);
				// Text is already updated inside handlePinToggle
			});
		}

		// Render messages
		messagesContainer.innerHTML = ""; // Clear potential loading/error states
		if (data.messages && data.messages.length > 0) {
			// Group messages to associate reasoning with assistant messages
			const processedMessages = [];
			let currentAssistantMessage = null;

			for (let i = 0; i < data.messages.length; i++) {
				const msg = data.messages[i];

				if (msg.role === "assistant-reasoning") {
					// Find the next assistant message to attach this reasoning to
					for (let j = i + 1; j < data.messages.length; j++) {
						if (data.messages[j].role === "assistant") {
							// Attach reasoning to the next assistant message
							data.messages[j].reasoning = msg;
							break;
						}
					}
				} else {
					processedMessages.push(msg);
				}
			}

			processedMessages.forEach((msg) => {
				const messageDiv = document.createElement("div");
				messageDiv.className = `message message-${escapeHtml(msg.role.toLowerCase())}`;
				messageDiv.dataset.filename = msg.filename;
				messageDiv.dataset.role = msg.role; // Store role for actions
				messageDiv.dataset.originalContent = msg.content; // Store original content for edit/fork

				// If this message has associated reasoning, display it first
				if (msg.reasoning) {
					const reasoningContainer = document.createElement("div");
					reasoningContainer.className = "message-reasoning-container";
					reasoningContainer.style.margin = "0 0 10px 0";

					// Create toggle header
					const reasoningHeader = document.createElement("div");
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

					const toggleIcon = document.createElement("span");
					toggleIcon.style.fontSize = "12px";
					toggleIcon.style.color = "#4a8ab7";
					toggleIcon.textContent = "▶"; // Right arrow when collapsed

					reasoningHeader.appendChild(reasoningLabel);
					reasoningHeader.appendChild(toggleIcon);

					// Create collapsible content
					const reasoningContent = document.createElement("div");
					reasoningContent.className = "message-reasoning";
					reasoningContent.style.backgroundColor = "#050505";
					reasoningContent.style.padding = "12px";
					reasoningContent.style.marginTop = "4px";
					reasoningContent.style.borderRadius = "5px";
					reasoningContent.style.color = "#a0a0a0";
					reasoningContent.style.display = "none"; // Hidden by default
					reasoningContent.style.whiteSpace = "pre-wrap";

					// Extract content from <think> tags if present
					let reasoningText = msg.reasoning.content;
					const thinkMatch = msg.reasoning.content.match(
						/^<think>([\s\S]*?)<\/think>$/,
					);
					if (thinkMatch) {
						reasoningText = thinkMatch[1];
					}

					reasoningContent.innerHTML = renderMarkdown(reasoningText);

					// Toggle handler
					reasoningHeader.addEventListener("click", () => {
						const isVisible = reasoningContent.style.display !== "none";
						reasoningContent.style.display = isVisible ? "none" : "block";
						toggleIcon.textContent = isVisible ? "▶" : "▼";
					});

					reasoningContainer.appendChild(reasoningHeader);
					reasoningContainer.appendChild(reasoningContent);
					messageDiv.appendChild(reasoningContainer);
				}

				// Wrapper for content to allow easy replacement (text <-> textarea)
				const contentWrapperDiv = document.createElement("div");
				contentWrapperDiv.className = "message-content-wrapper";
				contentWrapperDiv.innerHTML = renderMarkdown(msg.content); // Render markdown

				// New compact footer
				const footerDiv = document.createElement("div");
				footerDiv.className = "message-footer";

				const infoDiv = document.createElement("div");
				infoDiv.className = "message-info";

				// Role span removed - now shown in info modal instead

				// Actions (Edit, Archive) - this is now just a button container
				const actionsDiv = document.createElement("div");
				actionsDiv.className = "message-actions";

				const infoButton = createActionButton(ICON_INFO, "btn-info", () =>
					showMessageInfoModal(msg.filename, msg.content, msg.role),
				);
				infoButton.title = "Info";

				const editButton = createActionButton(ICON_PENCIL, "btn-edit", () =>
					toggleEditState(
						messageDiv,
						contentWrapperDiv,
						actionsDiv,
						msg.content,
						conversationId,
						msg.filename,
						msg.reasoning,
					),
				);
				editButton.title = "Edit"; // Tooltip for accessibility

				const forkButton = createActionButton(ICON_SPLIT, "btn-fork", () =>
					handleForkFromMessage(conversationId, msg.filename, msg.role),
				);
				forkButton.title = "Fork from here"; // Tooltip for accessibility

				const archiveButton = createActionButton(
					ICON_ARCHIVE,
					"btn-archive",
					() =>
						handleArchiveMessage(
							messageDiv,
							conversationId,
							msg.filename,
							msg.reasoning,
						),
				);
				archiveButton.title = "Archive"; // Tooltip for accessibility

				const copyButton = createActionButton(ICON_COPY, "btn-copy", () =>
					handleCopyMessage(msg.content),
				);
				copyButton.title = "Copy"; // Tooltip for accessibility

				actionsDiv.appendChild(infoButton);
				actionsDiv.appendChild(copyButton);
				actionsDiv.appendChild(editButton);
				actionsDiv.appendChild(forkButton);
				actionsDiv.appendChild(archiveButton);

				footerDiv.appendChild(infoDiv);
				footerDiv.appendChild(actionsDiv);

				messageDiv.appendChild(contentWrapperDiv);
				messageDiv.appendChild(footerDiv);
				messagesContainer.appendChild(messageDiv);
			});
		} else {
			messagesContainer.innerHTML =
				"<p>No messages found in this conversation.</p>";
		}

		// Render other files
		otherFilesContainer.innerHTML = ""; // Clear
		if (data.other_files && data.other_files.length > 0) {
			const divider = document.createElement("hr");
			divider.className = "other-files-divider";

			// Create collapsible container
			const collapsibleContainer = document.createElement("div");
			collapsibleContainer.className = "collapsible-section";

			// Create header with toggle
			const headerContainer = document.createElement("div");
			headerContainer.className = "collapsible-header";
			headerContainer.style.cursor = "pointer";
			headerContainer.style.display = "flex";
			headerContainer.style.alignItems = "center";
			headerContainer.style.justifyContent = "space-between";
			headerContainer.style.padding = "10px 0";

			const heading = document.createElement("h2");
			heading.textContent = "Other Files";
			heading.style.margin = "0";

			const toggleIcon = document.createElement("span");
			toggleIcon.style.fontSize = "14px";
			toggleIcon.style.color = "#4a8ab7";
			toggleIcon.textContent = "▶"; // Right arrow when collapsed

			headerContainer.appendChild(heading);
			headerContainer.appendChild(toggleIcon);

			// Create content container
			const contentContainer = document.createElement("div");
			contentContainer.className = "collapsible-content";
			contentContainer.style.display = "none"; // Collapsed by default

			const ul = document.createElement("ul");

			data.other_files.forEach((file) => {
				const li = document.createElement("li");
				li.className = "other-file-entry";

				const strong = document.createElement("strong");
				strong.textContent = escapeHtml(file.filename);
				li.appendChild(strong);

				if (file.is_text && file.content !== null) {
					const contentDisplayDiv = document.createElement("div");
					contentDisplayDiv.className = "other-file-content";
					const pre = document.createElement("pre");
					pre.textContent = file.content; // Raw text content
					contentDisplayDiv.appendChild(pre);
					li.appendChild(contentDisplayDiv);
				} else {
					const errorDisplayDiv = document.createElement("div");
					// Use binary style for error messages related to file content
					errorDisplayDiv.className =
						"other-file-content other-file-content-binary";
					errorDisplayDiv.textContent = escapeHtml(
						file.error_message || "[Unknown issue with file]",
					);
					li.appendChild(errorDisplayDiv);
				}
				ul.appendChild(li);
			});

			contentContainer.appendChild(ul);

			// Toggle handler
			headerContainer.addEventListener("click", () => {
				const isVisible = contentContainer.style.display !== "none";
				contentContainer.style.display = isVisible ? "none" : "block";
				toggleIcon.textContent = isVisible ? "▶" : "▼";
			});

			collapsibleContainer.appendChild(headerContainer);
			collapsibleContainer.appendChild(contentContainer);

			otherFilesContainer.appendChild(divider);
			otherFilesContainer.appendChild(collapsibleContainer);
		}

		// Render archived messages
		if (data.archived_messages && data.archived_messages.length > 0) {
			const archiveDivider = document.createElement("hr");
			archiveDivider.className = "archive-divider";

			// Create collapsible container for archived messages
			const archiveContainer = document.createElement("div");
			archiveContainer.className = "collapsible-section archive-section";

			// Create header with toggle
			const archiveHeader = document.createElement("div");
			archiveHeader.className = "collapsible-header";
			archiveHeader.style.cursor = "pointer";
			archiveHeader.style.display = "flex";
			archiveHeader.style.alignItems = "center";
			archiveHeader.style.justifyContent = "space-between";
			archiveHeader.style.padding = "10px 0";

			const archiveHeading = document.createElement("h2");
			archiveHeading.textContent = `Deleted Messages (${data.archived_messages.length})`;
			archiveHeading.style.margin = "0";
			archiveHeading.style.color = "#e0e0e0"; // White text like Other Files

			const archiveToggleIcon = document.createElement("span");
			archiveToggleIcon.style.fontSize = "14px";
			archiveToggleIcon.style.color = "#4a8ab7"; // Blue like Other Files
			archiveToggleIcon.textContent = "▶"; // Right arrow when collapsed

			archiveHeader.appendChild(archiveHeading);
			archiveHeader.appendChild(archiveToggleIcon);

			// Create content container
			const archiveContent = document.createElement("div");
			archiveContent.className = "collapsible-content archive-content";
			archiveContent.style.display = "none"; // Collapsed by default

			// Group archived messages by conversation order
			const groupedArchived = [];
			let currentGroup = null;

			// Sort archived messages by filename to ensure correct order
			const sortedArchived = [...data.archived_messages].sort((a, b) =>
				a.filename.localeCompare(b.filename),
			);

			for (let i = 0; i < sortedArchived.length; i++) {
				const msg = sortedArchived[i];

				if (msg.role === "assistant-reasoning") {
					// Find the next assistant message to attach this reasoning to
					for (let j = i + 1; j < sortedArchived.length; j++) {
						if (sortedArchived[j].role === "assistant") {
							// Attach reasoning to the next assistant message
							sortedArchived[j].reasoning = msg;
							break;
						}
					}
				} else {
					groupedArchived.push(msg);
				}
			}

			// Render archived messages
			groupedArchived.forEach((msg) => {
				const messageDiv = document.createElement("div");
				messageDiv.className = `message message-${escapeHtml(msg.role.toLowerCase())} archived-message`;
				messageDiv.dataset.filename = msg.filename;
				messageDiv.dataset.role = msg.role;

				// If this message has associated reasoning, display it first
				if (msg.reasoning) {
					const reasoningContainer = document.createElement("div");
					reasoningContainer.className = "message-reasoning-container";
					reasoningContainer.style.margin = "0 0 10px 0";

					// Create toggle header
					const reasoningHeader = document.createElement("div");
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

					const toggleIcon = document.createElement("span");
					toggleIcon.style.fontSize = "12px";
					toggleIcon.style.color = "#4a8ab7";
					toggleIcon.textContent = "▶"; // Right arrow when collapsed

					reasoningHeader.appendChild(reasoningLabel);
					reasoningHeader.appendChild(toggleIcon);

					// Create collapsible content
					const reasoningContent = document.createElement("div");
					reasoningContent.className = "message-reasoning";
					reasoningContent.style.backgroundColor = "#050505";
					reasoningContent.style.padding = "12px";
					reasoningContent.style.marginTop = "4px";
					reasoningContent.style.borderRadius = "5px";
					reasoningContent.style.color = "#a0a0a0";
					reasoningContent.style.display = "none"; // Hidden by default
					reasoningContent.style.whiteSpace = "pre-wrap";

					// Extract content from <think> tags if present
					let reasoningText = msg.reasoning.content;
					const thinkMatch = msg.reasoning.content.match(
						/^<think>([\s\S]*?)<\/think>$/,
					);
					if (thinkMatch) {
						reasoningText = thinkMatch[1];
					}

					reasoningContent.innerHTML = renderMarkdown(reasoningText);

					// Toggle handler
					reasoningHeader.addEventListener("click", () => {
						const isVisible = reasoningContent.style.display !== "none";
						reasoningContent.style.display = isVisible ? "none" : "block";
						toggleIcon.textContent = isVisible ? "▶" : "▼";
					});

					reasoningContainer.appendChild(reasoningHeader);
					reasoningContainer.appendChild(reasoningContent);
					messageDiv.appendChild(reasoningContainer);
				}

				// Message content
				const contentDiv = document.createElement("div");
				contentDiv.className = "message-content";
				contentDiv.textContent = msg.content;

				// Footer with role and restore button
				const footerDiv = document.createElement("div");
				footerDiv.className = "message-footer";

				const infoDiv = document.createElement("div");
				infoDiv.className = "message-info";

				// Role span removed - now shown in info modal instead

				// Restore button
				const actionsDiv = document.createElement("div");
				actionsDiv.className = "message-actions";

				const restoreButton = document.createElement("button");
				restoreButton.className = "btn-action btn-restore";
				restoreButton.innerHTML =
					'<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-rotate-ccw-icon lucide-rotate-ccw"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>';
				restoreButton.title = "Restore message";
				restoreButton.onclick = () => {
					// TODO: Implement restore functionality
					alert("Restore functionality not yet implemented");
				};

				actionsDiv.appendChild(restoreButton);

				footerDiv.appendChild(infoDiv);
				footerDiv.appendChild(actionsDiv);

				messageDiv.appendChild(contentDiv);
				messageDiv.appendChild(footerDiv);

				archiveContent.appendChild(messageDiv);
			});

			// Toggle handler
			archiveHeader.addEventListener("click", () => {
				const isVisible = archiveContent.style.display !== "none";
				archiveContent.style.display = isVisible ? "none" : "block";
				archiveToggleIcon.textContent = isVisible ? "▶" : "▼";
			});

			archiveContainer.appendChild(archiveHeader);
			archiveContainer.appendChild(archiveContent);

			messagesContainer.appendChild(archiveDivider);
			messagesContainer.appendChild(archiveContainer);
		}

		// After rendering messages and other files, set up the input area
		setupMessageInputArea(conversationId);
		updateSplitButtonState(conversationId); // Set initial button state

		// Check if this is a forked conversation with actions to perform
		const forkActionKey = `fork-action-${conversationId}`;
		const forkActionData = localStorage.getItem(forkActionKey);
		if (forkActionData) {
			localStorage.removeItem(forkActionKey); // Clean up immediately
			try {
				const forkInfo = JSON.parse(forkActionData);
				processForkActions(conversationId, forkInfo);
			} catch (error) {
				console.error("Error processing fork actions:", error);
			}
		} else {
			// Check if we should trigger generation after a reload
			const generateKey = `fork-generate-${conversationId}`;
			if (localStorage.getItem(generateKey)) {
				localStorage.removeItem(generateKey);
				// Small delay to ensure everything is ready
				setTimeout(() => {
					const primaryBtn = document.getElementById("primary-action-btn");
					const dropdownToggleBtn = document.getElementById(
						"dropdown-toggle-btn",
					);
					const allButtons = [primaryBtn, dropdownToggleBtn].filter(Boolean);

					if (allButtons.length > 0) {
						handleGenAssistant(conversationId, allButtons);
					} else {
						// Fallback: click the button directly
						const genButton = document.querySelector(
							'button[data-action="gen-assistant"]',
						);
						if (genButton) {
							genButton.click();
						}
					}
				}, 500);
			}
		}

		// Setup modal button listeners
		if (modalForkBtn) {
			const newForkButton = modalForkBtn.cloneNode(true);
			modalForkBtn.parentNode.replaceChild(newForkButton, modalForkBtn);
			newForkButton.disabled = false;
			newForkButton.addEventListener("click", () => {
				settingsModal.classList.add("hidden"); // Close modal
				handleForkConversation(conversationId);
			});
		}

		if (modalShareBtn) {
			const newShareButton = modalShareBtn.cloneNode(true);
			modalShareBtn.parentNode.replaceChild(newShareButton, modalShareBtn);
			newShareButton.disabled = false;
			newShareButton.addEventListener("click", () => {
				settingsModal.classList.add("hidden"); // Close settings modal
				showShareModal(conversationId);
			});
		}

		// Setup settings modal toggle
		if (settingsToggleBtn) {
			settingsToggleBtn.addEventListener("click", () => {
				settingsModal.classList.remove("hidden");
				// Don't focus on title input when opened via settings button
			});
		}

		// Make h1 title clickable to open modal
		if (mainTitleDisplayElement) {
			mainTitleDisplayElement.addEventListener("click", () => {
				settingsModal.classList.remove("hidden");
				// Focus on title input when opened via h1 click
				if (modalTitleInput) {
					setTimeout(() => {
						modalTitleInput.focus();
						modalTitleInput.select(); // Select all text for easy editing
					}, 100);
				}
			});
		}

		// Setup modal close button
		if (settingsCloseBtn) {
			settingsCloseBtn.addEventListener("click", () => {
				settingsModal.classList.add("hidden");
			});
		}

		// Close modal when clicking outside
		if (settingsModal) {
			settingsModal.addEventListener("click", (event) => {
				if (event.target === settingsModal) {
					settingsModal.classList.add("hidden");
				}
			});
		}

		// Auto-scroll to latest message on page load
		setTimeout(() => {
			jumpToLatestMessage();
		}, 100); // Small delay to ensure DOM is fully rendered
	} catch (error) {
		handleError(
			`Failed to load conversation: ${safeConvId}.`,
			messagesContainer,
		);
		console.error(`Error loading conversation ${conversationId}:`, error);
		otherFilesContainer.innerHTML = ""; // Clear other files section on error too
		// Ensure input area is not set up or is cleared on error
		const messageInputArea = document.getElementById("message-input-area");
		if (messageInputArea) messageInputArea.innerHTML = "";
	}
}
async function updateConversationTitle(conversationId, newTitle, inputElement) {
	// Clear previous errors specifically for this input action
	clearErrorMessages(inputElement.closest("li"));

	try {
		const response = await authFetch(
			`/api/conversation/${encodeURIComponent(conversationId)}/title`,
			{
				method: "PUT",
				headers: {
					"Content-Type": "application/json",
				},
				body: JSON.stringify({ title: newTitle }),
			},
		);

		if (!response.ok) {
			const errorData = await response
				.json()
				.catch(() => ({ detail: "Unknown error updating title." }));
			throw new Error(
				errorData.detail || `HTTP error! status: ${response.status}`,
			);
		}

		const responseData = await response.json();
		// Backend only returns {"status": "success"}, so use the title we sent
		const savedTitle = newTitle;

		// Visually indicate success briefly (optional)
		inputElement.style.borderColor = "#6ec8ff"; // Blue theme color
		setTimeout(() => {
			inputElement.style.borderColor = "";
		}, 1500);

		inputElement.value = escapeHtml(savedTitle === "-" ? "" : savedTitle);
		inputElement.dataset.originalTitle = savedTitle;
		console.log(`Title for ${conversationId} updated to "${savedTitle}"`);

		// Show success toast
		showToast("Title updated", "success");
	} catch (error) {
		console.error("Failed to update title:", error);
		handleError(
			`Error updating title: ${error.message}`,
			inputElement.parentElement,
		);
		throw error; // Re-throw to allow caller to handle UI revert
	}
}

async function updateConversationModel(conversationId, newModel, inputElement) {
	clearErrorMessages(
		inputElement.closest(".model-edit-container") || inputElement.parentElement,
	);

	try {
		const response = await authFetch(
			`/api/conversation/${encodeURIComponent(conversationId)}/model`,
			{
				method: "PUT",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ model: newModel }), // newModel can be empty string
			},
		);

		if (!response.ok) {
			const errorData = await response
				.json()
				.catch(() => ({ detail: "Unknown error updating model." }));
			throw new Error(
				errorData.detail || `HTTP error! status: ${response.status}`,
			);
		}
		const responseData = await response.json();
		// Backend only returns {"status": "success"}, so use the model we sent
		// If empty string was sent, backend will use default, so we should too
		const savedModel = newModel || DEFAULT_MODEL_NAME;

		inputElement.style.borderColor = "#6ec8ff"; // Blue theme color
		setTimeout(() => {
			inputElement.style.borderColor = "";
		}, 1500);

		inputElement.value = escapeHtml(savedModel); // Update input to what was actually saved
		inputElement.dataset.originalModel = savedModel;
		console.log(`Model for ${conversationId} updated to "${savedModel}"`);

		// Show success toast
		showToast("Model updated", "success");
	} catch (error) {
		console.error("Failed to update model:", error);
		handleError(
			`Error updating model: ${error.message}`,
			inputElement.parentElement,
		);
		throw error; // Re-throw to allow caller to handle UI revert
	}
}
async function handlePinToggle(conversationId, buttonElement) {
	if (buttonElement) buttonElement.disabled = true;
	const titleSection = document.querySelector(".title-section");
	if (titleSection) clearErrorMessages(titleSection);

	try {
		const response = await authFetch(
			`/api/conversation/${encodeURIComponent(conversationId)}/pin-toggle`,
			{
				method: "POST",
				headers: {
					// No Content-Type needed for empty body POST
				},
			},
		);

		if (!response.ok) {
			let errorDetail = "Failed to toggle pin status.";
			try {
				const errorData = await response.json();
				if (errorData && errorData.detail) {
					errorDetail = errorData.detail;
				}
			} catch (e) {
				errorDetail += ` Server responded with: ${response.status} ${response.statusText}`;
			}
			throw new Error(errorDetail);
		}

		const responseData = await response.json(); // Expects {"is_pinned": boolean, "status": "..."}
		if (buttonElement) {
			const pinTextElem = buttonElement.querySelector("#modal-pin-text");
			if (pinTextElem) {
				pinTextElem.textContent = responseData.is_pinned
					? "Unpin Conversation"
					: "Pin Conversation";
			} else {
				// Fallback for elements without the span structure
				buttonElement.textContent = responseData.is_pinned ? "Unpin" : "Pin";
			}
		}

		// Update the h1 title to show/hide pin icon
		const mainTitleDisplayElement = document.getElementById(
			"conversation-id-display",
		);
		const modalTitleInput = document.getElementById("modal-title-input");
		if (mainTitleDisplayElement && modalTitleInput) {
			const currentTitle = modalTitleInput.dataset.originalTitle || "-";
			const displayPageTitle =
				currentTitle && currentTitle !== "-"
					? escapeHtml(currentTitle)
					: `Conversation ${conversationId}`;

			// Clear the h1 and rebuild with pin icon if needed
			mainTitleDisplayElement.innerHTML = "";

			if (responseData.is_pinned) {
				// Add pin icon
				const pinIcon = document.createElement("span");
				pinIcon.className = "title-pin-icon";
				pinIcon.style.display = "inline-block";
				pinIcon.style.marginRight = "8px";
				pinIcon.style.verticalAlign = "middle";
				pinIcon.innerHTML = ICON_PIN.replace(
					'width="24"',
					'width="20"',
				).replace('height="24"', 'height="20"');
				mainTitleDisplayElement.appendChild(pinIcon);
			}

			// Add title text
			const titleSpan = document.createElement("span");
			titleSpan.textContent = displayPageTitle;
			mainTitleDisplayElement.appendChild(titleSpan);
		}

		// Show success toast
		const action = responseData.is_pinned ? "pinned" : "unpinned";
		showToast(`Conversation ${action}`, "success");
	} catch (error) {
		console.error("Error toggling pin status:", error);
		handleError(
			error.message,
			titleSection || (buttonElement ? buttonElement.parentElement : null),
		);
	} finally {
		if (buttonElement) buttonElement.disabled = false;
	}
}
async function processForkActions(conversationId, forkInfo) {
	// Process fork actions: edit message if needed, delete messages, and trigger generation
	try {
		// Get all messages from the page
		const messages = document.querySelectorAll(
			"#messages-container .message:not(.archived-message)",
		);

		// Find the index of the target message
		let targetIndex = -1;
		for (let i = 0; i < messages.length; i++) {
			const msgFilename = messages[i].dataset.filename;
			if (msgFilename === forkInfo.fromMessage) {
				targetIndex = i;
				break;
			}
		}

		if (targetIndex === -1) {
			console.error("Could not find target message for fork action");
			return;
		}

		// Edit the message if editedContent is provided
		if (forkInfo.editedContent) {
			showToast("Applying edit to forked message...", "info");
			try {
				const response = await authFetch(
					`/api/conversation/${encodeURIComponent(conversationId)}/message/${encodeURIComponent(forkInfo.fromMessage)}/edit`,
					{
						method: "PUT",
						headers: { "Content-Type": "application/json" },
						body: JSON.stringify({ content: forkInfo.editedContent }),
					},
				);

				if (!response.ok) {
					const errorData = await response
						.json()
						.catch(() => ({ detail: "Failed to edit message." }));
					throw new Error(errorData.detail || `HTTP error ${response.status}`);
				}
			} catch (error) {
				console.error("Error editing message:", error);
				showToast(`Failed to edit message: ${error.message}`, "error");
				// Continue with the rest of the fork actions even if edit fails
			}
		}

		// Determine which messages to delete
		let messagesToDelete = [];
		if (forkInfo.deleteAfter && forkInfo.messageRole === "assistant") {
			// Delete from and including the assistant message
			for (let i = targetIndex; i < messages.length; i++) {
				const msgFilename = messages[i].dataset.filename;
				if (msgFilename) {
					messagesToDelete.push(msgFilename);
				}
			}
		} else {
			// Delete all messages after the target (for system/user messages)
			for (let i = targetIndex + 1; i < messages.length; i++) {
				const msgFilename = messages[i].dataset.filename;
				if (msgFilename) {
					messagesToDelete.push(msgFilename);
				}
			}
		}

		// Delete the messages
		let deletedCount = 0;
		if (messagesToDelete.length > 0) {
			showToast(`Cleaning up ${messagesToDelete.length} message(s)...`, "info");

			for (const filename of messagesToDelete) {
				try {
					// Archive the message instead of hard delete
					const response = await authFetch(
						`/api/conversation/${encodeURIComponent(conversationId)}/message/${encodeURIComponent(filename)}/archive`,
						{
							method: "POST",
						},
					);

					if (response.ok) {
						deletedCount++;
					} else {
						console.error(`Failed to archive message ${filename}`);
					}
				} catch (error) {
					console.error(`Error archiving message ${filename}:`, error);
				}
			}

			// If we deleted messages, reload to get the updated state
			if (deletedCount > 0) {
				showToast(`Archived ${deletedCount} message(s). Reloading...`, "info");
				// Store that we should trigger generation after reload
				if (forkInfo.triggerGenerate) {
					localStorage.setItem(`fork-generate-${conversationId}`, "true");
				}
				// Reload the conversation to reflect changes
				setTimeout(() => {
					loadConversationDetails(conversationId);
				}, 500);
				return;
			}
		}

		// If we only edited without deleting messages, reload to show the edit
		if (forkInfo.editedContent && messagesToDelete.length === 0) {
			showToast("Edit applied. Reloading...", "info");
			if (forkInfo.triggerGenerate) {
				localStorage.setItem(`fork-generate-${conversationId}`, "true");
			}
			setTimeout(() => {
				loadConversationDetails(conversationId);
			}, 500);
			return;
		}

		// If no messages were deleted and no edit, trigger generation immediately if requested
		if (forkInfo.triggerGenerate && !forkInfo.editedContent) {
			showToast("Starting generation...", "info");
			// Get the buttons for handleGenAssistant
			const primaryBtn = document.getElementById("primary-action-btn");
			const dropdownToggleBtn = document.getElementById("dropdown-toggle-btn");
			const allButtons = [primaryBtn, dropdownToggleBtn].filter(Boolean);

			// Small delay to ensure page is ready
			setTimeout(() => {
				if (allButtons.length > 0) {
					handleGenAssistant(conversationId, allButtons);
				} else {
					// Fallback: click the button directly
					const genButton = document.querySelector(
						'button[data-action="gen-assistant"]',
					);
					if (genButton) {
						genButton.click();
					}
				}
			}, 500);
		}
	} catch (error) {
		console.error("Error processing fork actions:", error);
		showToast("Error processing fork actions", "error");
	}
}

async function handleForkFromMessage(
	conversationId,
	messageFilename,
	messageRole,
) {
	// For user and system messages, enter fork-edit mode
	// For assistant messages, fork immediately
	if (messageRole === "user" || messageRole === "system") {
		// Find the message element
		const messageElement = document.querySelector(
			`[data-filename="${messageFilename}"]`,
		);
		if (!messageElement) {
			showToast("Could not find message element", "error");
			return;
		}

		// Find the content wrapper and actions div
		const contentWrapperDiv = messageElement.querySelector(
			".message-content-wrapper",
		);
		const actionsDiv = messageElement.querySelector(".message-actions");

		if (!contentWrapperDiv || !actionsDiv) {
			showToast("Could not find message components", "error");
			return;
		}

		// Get the original content from the data attribute
		const currentContent =
			messageElement.dataset.originalContent || contentWrapperDiv.textContent;

		// Enter fork-edit mode
		toggleForkEditState(
			messageElement,
			contentWrapperDiv,
			actionsDiv,
			currentContent,
			conversationId,
			messageFilename,
			messageRole,
		);
	} else {
		// For assistant messages, fork immediately as before
		executeForkFromMessage(conversationId, messageFilename, messageRole);
	}
}

async function executeForkFromMessage(
	conversationId,
	messageFilename,
	messageRole,
	editedContent = null,
) {
	// Fork the conversation first
	try {
		const response = await authFetch(
			`/api/conversation/${encodeURIComponent(conversationId)}/fork`,
			{
				method: "POST",
			},
		);

		if (!response.ok) {
			let errorDetail = "Failed to fork conversation.";
			try {
				const errorData = await response.json();
				if (errorData && errorData.detail) {
					errorDetail = errorData.detail;
				}
			} catch (e) {
				errorDetail += ` Server responded with: ${response.status} ${response.statusText}`;
			}
			throw new Error(errorDetail);
		}

		const responseData = await response.json();
		if (responseData && responseData.conversation_id) {
			const newConversationId = responseData.conversation_id;

			// Store the fork info in localStorage for the new page to process
			const forkInfo = {
				fromMessage: messageFilename,
				messageRole: messageRole,
				deleteAfter: messageRole === "assistant", // Delete including assistant message
				triggerGenerate: true,
				editedContent: editedContent, // Include edited content if provided
			};
			localStorage.setItem(
				`fork-action-${newConversationId}`,
				JSON.stringify(forkInfo),
			);

			// Redirect to the new forked conversation
			window.location.href = `/c/${encodeURIComponent(newConversationId)}`;
		} else {
			throw new Error(
				"Fork successful, but new conversation ID was not returned.",
			);
		}
	} catch (error) {
		console.error("Error forking conversation from message:", error);
		showToast(error.message, "error");
	}
}
async function handleForkConversation(conversationId) {
	const forkBtn = document.getElementById("fork-conversation-btn");
	if (forkBtn) forkBtn.disabled = true;

	const titleSection = document.querySelector(".title-section");
	if (titleSection) clearErrorMessages(titleSection);

	try {
		const response = await authFetch(
			`/api/conversation/${encodeURIComponent(conversationId)}/fork`,
			{
				method: "POST",
				headers: {
					// "Content-Type": "application/json", // Not strictly needed as no body is sent
				},
			},
		);

		if (!response.ok) {
			let errorDetail = "Failed to fork conversation.";
			try {
				const errorData = await response.json();
				if (errorData && errorData.detail) {
					errorDetail = errorData.detail;
				}
			} catch (e) {
				errorDetail += ` Server responded with: ${response.status} ${response.statusText}`;
			}
			throw new Error(errorDetail);
		}

		const responseData = await response.json();
		if (responseData && responseData.conversation_id) {
			window.location.href = `/c/${encodeURIComponent(responseData.conversation_id)}`;
		} else {
			throw new Error(
				"Fork successful, but new conversation ID was not returned.",
			);
		}
	} catch (error) {
		console.error("Error forking conversation:", error);
		// Display error near the title section or button's parent
		handleError(
			error.message,
			titleSection || (forkBtn ? forkBtn.parentElement : null),
		);
		if (forkBtn) forkBtn.disabled = false; // Re-enable on error
	}
}

export {
	loadConversationsList,
	handleCreateConversation,
	loadConversationDetails,
	updateConversationTitle,
	updateConversationModel,
	handlePinToggle,
	processForkActions,
	handleForkFromMessage,
	executeForkFromMessage,
	handleForkConversation,
};

// Set the loadConversationDetails function in message-input module to avoid circular dependency
setLoadConversationDetails(loadConversationDetails);
