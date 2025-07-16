document.addEventListener("DOMContentLoaded", () => {
	// Check if logged in
	if (!localStorage.getItem("username") || !localStorage.getItem("password")) {
		window.location.href = "/login.html";
		return;
	}

	// Add auth headers to all fetch requests
	const authFetch = (url, options = {}) => {
		const username = localStorage.getItem("username");
		const password = localStorage.getItem("password");

		if (!username || !password) {
			window.location.href = "/login.html";
			return Promise.reject(new Error("Not authenticated"));
		}

		const headers = {
			"X-Username": username,
			"X-Password": password,
			...options.headers,
		};

		return fetch(url, { ...options, headers }).then((response) => {
			if (response.status === 401) {
				// Clear credentials and redirect to login
				localStorage.removeItem("username");
				localStorage.removeItem("password");
				window.location.href = "/login.html";
				return Promise.reject(new Error("Authentication failed"));
			}
			return response;
		});
	};
	document.addEventListener("click", (event) => {
		const menu = document.getElementById("action-dropdown-menu");
		if (!menu || menu.classList.contains("hidden")) return;

		// If the click is NOT on the toggle button AND NOT inside the menu, hide it.
		if (
			!event.target.closest("#dropdown-toggle-btn") &&
			!event.target.closest("#action-dropdown-menu")
		) {
			menu.classList.add("hidden");
		}
	});

	const DEFAULT_MODEL_NAME = "openrouter/deepseek/deepseek-chat-v3-0324:free";

	// Lucide Icon SVG Strings
	const ICON_PIN = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-pin-icon lucide-pin"><path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/></svg>`;
	const ICON_INFO = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-info-icon lucide-info"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>`;
	const ICON_PENCIL = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-pen-line-icon lucide-pen-line"><path d="M12 20h9"/><path d="M16.376 3.622a1 1 0 0 1 3.002 3.002L7.368 18.635a2 2 0 0 1-.855.506l-2.872.838a.5.5 0 0 1-.62-.62l.838-2.872a2 2 0 0 1 .506-.854z"/></svg>`;
	const ICON_ARCHIVE = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-archive-icon lucide-archive"><rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/><path d="M10 12h4"/></svg>`;
	const ICON_SAVE = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-save-icon lucide-save"><path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/><path d="M7 3v4a1 1 0 0 0 1 1h7"/></svg>`;
	const ICON_X = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-x-icon lucide-x"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>`;
	const ICON_SHARE = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-share-2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" x2="15.42" y1="13.51" y2="17.49"/><line x1="15.41" x2="8.59" y1="6.51" y2="10.49"/></svg>`;

	// Display username
	const username = localStorage.getItem("username");
	const usernameDisplay = document.getElementById("username-display");
	if (usernameDisplay) {
		usernameDisplay.textContent = `Logged in as: ${username}`;
	}

	// Setup logout button
	const logoutBtn = document.getElementById("logout-btn");
	if (logoutBtn) {
		logoutBtn.addEventListener("click", () => {
			localStorage.removeItem("username");
			localStorage.removeItem("password");
			window.location.href = "/login.html";
		});
	}

	const path = window.location.pathname;

	if (path === "/") {
		loadConversationsList();
		const createBtn = document.getElementById("create-conversation-btn");
		if (createBtn) {
			createBtn.addEventListener("click", handleCreateConversation);
		}
	} else if (path.startsWith("/c/")) {
		const parts = path.split("/");
		const conversationId = parts[parts.length - 1];
		if (conversationId) {
			loadConversationDetails(conversationId);
			// setupMessageInputArea will be called from within loadConversationDetails
		} else {
			handleError("Conversation ID missing in URL.");
		}
	}

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
				buttonContainer ||
					document.getElementById("conversation-list-container"),
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
		const titleEditInput = document.getElementById("conversation-title-input");
		const modelEditInput = document.getElementById("conversation-model-input");
		const pinToggleButton = document.getElementById("pin-toggle-btn");
		const jumpToLatestBtn = document.getElementById("jump-to-latest-btn");
		const messagesContainer = document.getElementById("messages-container");
		const otherFilesContainer = document.getElementById(
			"other-files-container",
		);

		const safeConvId = escapeHtml(conversationId);

		// Initial state for inputs and buttons
		document.title = `Loading conversation...`;
		mainTitleDisplayElement.textContent = `Loading conversation...`;
		titleEditInput.value = "";
		titleEditInput.disabled = true;
		modelEditInput.value = "";
		modelEditInput.disabled = true;
		if (pinToggleButton) {
			pinToggleButton.disabled = true;
			pinToggleButton.textContent = "Pin"; // Default before loading
		}
		if (jumpToLatestBtn) {
			jumpToLatestBtn.disabled = true;
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
			const updateDisplayedTitle = (currentTitle) => {
				const displayPageTitle =
					currentTitle && currentTitle !== "-"
						? escapeHtml(currentTitle)
						: `Conversation ${safeConvId}`;
				document.title = displayPageTitle;
				mainTitleDisplayElement.textContent = displayPageTitle;
			};
			updateDisplayedTitle(convTitle);
			titleEditInput.value = escapeHtml(convTitle === "-" ? "" : convTitle);
			titleEditInput.dataset.originalTitle = convTitle;
			titleEditInput.disabled = false;

			titleEditInput.addEventListener("blur", async () => {
				let newTitleAttempt = titleEditInput.value.trim();
				const originalTitle = titleEditInput.dataset.originalTitle;

				if (newTitleAttempt === "") {
					newTitleAttempt = "-"; // Default to "-" if input is cleared
				}

				if (newTitleAttempt !== originalTitle) {
					try {
						await updateConversationTitle(
							conversationId,
							newTitleAttempt,
							titleEditInput,
						);
						// updateConversationTitle handles updating dataset.originalTitle and input value on success
						updateDisplayedTitle(titleEditInput.dataset.originalTitle); // Update H1 and document title
					} catch (error) {
						titleEditInput.value = escapeHtml(
							originalTitle === "-" ? "" : originalTitle,
						);
					}
				} else {
					titleEditInput.value = escapeHtml(
						originalTitle === "-" ? "" : originalTitle,
					);
				}
			});
			titleEditInput.addEventListener("keypress", (event) => {
				if (event.key === "Enter") titleEditInput.blur();
			});

			// --- Model Handling ---
			const convModel = data.model || DEFAULT_MODEL_NAME; // Backend ensures default if missing/empty
			modelEditInput.value = escapeHtml(convModel);
			modelEditInput.dataset.originalModel = convModel;
			modelEditInput.disabled = false;

			modelEditInput.addEventListener("blur", async () => {
				let newModelAttempt = modelEditInput.value.trim(); // Can be empty
				const originalModel = modelEditInput.dataset.originalModel;

				if (newModelAttempt !== originalModel) {
					try {
						await updateConversationModel(
							conversationId,
							newModelAttempt,
							modelEditInput,
						);
						// updateConversationModel handles updating dataset.originalModel and input value
					} catch (error) {
						modelEditInput.value = escapeHtml(originalModel);
					}
				} else {
					// Ensure field shows the clean originalModel if user just added/removed spaces
					modelEditInput.value = escapeHtml(originalModel);
				}
			});
			modelEditInput.addEventListener("keypress", (event) => {
				if (event.key === "Enter") modelEditInput.blur();
			});

			// --- Pin/Unpin Button Setup ---
			if (pinToggleButton) {
				pinToggleButton.textContent = data.is_pinned ? "Unpin" : "Pin";
				pinToggleButton.disabled = false;
				// It's better to use addEventListener if this function might be called multiple times,
				// but for a full page/details load, direct onclick assignment is often simpler.
				// To be safe and avoid multiple listeners if this logic could be re-run without full DOM replacement:
				const newPinButton = pinToggleButton.cloneNode(true); // Clone to remove old listeners
				pinToggleButton.parentNode.replaceChild(newPinButton, pinToggleButton);
				newPinButton.addEventListener("click", () =>
					handlePinToggle(conversationId, newPinButton),
				);

				// Update the reference
				// pinToggleButton = newPinButton; // if pinToggleButton is used later in this function
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
					messageDiv.dataset.filename = msg.filename; // Store filename for actions

					// If this message has associated reasoning, display it first
					if (msg.reasoning) {
						const reasoningContainer = document.createElement("div");
						reasoningContainer.className = "message-reasoning-container";
						reasoningContainer.style.margin = "10px 0";

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

						reasoningContent.textContent = reasoningText;

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
					contentWrapperDiv.textContent = msg.content; // Initial content display

					// New compact footer
					const footerDiv = document.createElement("div");
					footerDiv.className = "message-footer";

					const infoDiv = document.createElement("div");
					infoDiv.className = "message-info";

					const roleSpan = document.createElement("span");
					roleSpan.className = "message-role";
					roleSpan.textContent = escapeHtml(msg.role);

					infoDiv.appendChild(roleSpan);

					// Actions (Edit, Archive) - this is now just a button container
					const actionsDiv = document.createElement("div");
					actionsDiv.className = "message-actions";

					const infoButton = createActionButton(ICON_INFO, "btn-info", () =>
						showMessageInfoModal(msg.filename, msg.content),
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

					actionsDiv.appendChild(infoButton);
					actionsDiv.appendChild(editButton);
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

					// If this message has associated reasoning, display it first
					if (msg.reasoning) {
						const reasoningContainer = document.createElement("div");
						reasoningContainer.className = "message-reasoning-container";
						reasoningContainer.style.margin = "10px 0";

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

						reasoningContent.textContent = reasoningText;

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

					const roleSpan = document.createElement("span");
					roleSpan.className = "message-role";
					roleSpan.textContent = escapeHtml(msg.role);

					infoDiv.appendChild(roleSpan);

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

			// Setup Fork button listener
			const forkButton = document.getElementById("fork-conversation-btn");
			if (forkButton) {
				// Clone the button to remove any previously attached event listeners
				const newForkButton = forkButton.cloneNode(true);
				forkButton.parentNode.replaceChild(newForkButton, forkButton);

				// Ensure the button is enabled (it might have been disabled from a previous action/error)
				newForkButton.disabled = false;

				newForkButton.addEventListener("click", () => {
					handleForkConversation(conversationId);
				});
			} else {
				console.warn("Fork button (#fork-conversation-btn) not found in DOM.");
			}

			// Setup Share button listener
			const shareButton = document.getElementById("share-conversation-btn");
			if (shareButton) {
				const newShareButton = shareButton.cloneNode(true);
				shareButton.parentNode.replaceChild(newShareButton, shareButton);
				newShareButton.disabled = false;

				newShareButton.addEventListener("click", () => {
					showShareModal(conversationId);
				});
			}

			// Setup Jump to Latest button listener
			const jumpToLatestButton = document.getElementById("jump-to-latest-btn");
			if (jumpToLatestButton) {
				// Clone to remove old listeners, consistent with other buttons
				const newJumpButton = jumpToLatestButton.cloneNode(true);
				jumpToLatestButton.parentNode.replaceChild(
					newJumpButton,
					jumpToLatestButton,
				);
				newJumpButton.disabled = false; // Enable the button

				newJumpButton.addEventListener("click", jumpToLatestMessage);
			} else {
				console.warn(
					"Jump to latest button (#jump-to-latest-btn) not found in DOM.",
				);
			}
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

	function setupMessageInputArea(conversationId) {
		let messageInputArea = document.getElementById("message-input-area");

		// Clear previous input area if any (e.g., on reload/re-render)
		if (messageInputArea) {
			messageInputArea.remove();
		}

		messageInputArea = document.createElement("div");
		messageInputArea.id = "message-input-area";

		const textarea = document.createElement("textarea");
		textarea.id = "new-message-content";
		textarea.placeholder = "Enter message content...";
		// textarea.rows = 4; // Replaced by dynamic height adjustment and CSS min-height
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
		}

		textarea.addEventListener("input", () =>
			adjustTextareaHeightOnInput(textarea),
		);
		// Initial call to set height will be done after textarea is appended to DOM.

		const buttonsDiv = document.createElement("div");
		buttonsDiv.id = "message-buttons";

		// Create split button structure
		const primaryBtn = document.createElement("button");
		primaryBtn.id = "primary-action-btn";

		const dropdownToggleBtn = document.createElement("button");
		dropdownToggleBtn.id = "dropdown-toggle-btn";
		dropdownToggleBtn.textContent = "▼";
		dropdownToggleBtn.addEventListener("click", () => {
			const dropdownMenu = document.getElementById("action-dropdown-menu");
			if (dropdownMenu) {
				dropdownMenu.classList.toggle("hidden");
			}
		});

		const dropdownMenu = document.createElement("div");
		dropdownMenu.id = "action-dropdown-menu";
		dropdownMenu.classList.add("hidden");

		buttonsDiv.appendChild(primaryBtn);
		buttonsDiv.appendChild(dropdownToggleBtn);
		buttonsDiv.appendChild(dropdownMenu);

		messageInputArea.appendChild(textarea);
		messageInputArea.appendChild(buttonsDiv);

		// Append the whole message input area directly to the body for fixed positioning
		document.body.appendChild(messageInputArea);
		adjustTextareaHeightOnInput(textarea); // Initial height adjustment
	}

	function updateSplitButtonState(conversationId) {
		const primaryBtn = document.getElementById("primary-action-btn");
		const dropdownToggleBtn = document.getElementById("dropdown-toggle-btn");
		const dropdownMenu = document.getElementById("action-dropdown-menu");
		const textarea = document.getElementById("new-message-content");
		if (!primaryBtn || !dropdownToggleBtn || !dropdownMenu || !textarea) return;

		const allButtons = [primaryBtn, dropdownToggleBtn]; // Dropdown buttons will be added.

		const messages = document.querySelectorAll("#messages-container .message");
		const lastMessage =
			messages.length > 0 ? messages[messages.length - 1] : null;
		const lastMessageIsUser =
			lastMessage && lastMessage.classList.contains("message-user");

		const createActionHandler = (action) => {
			if (action.gen) {
				return () => handleGenAssistant(conversationId, allButtons);
			}
			return () =>
				handleAddMessage(conversationId, action.role, textarea, allButtons);
		};

		const actions = {
			addUser: {
				text: "Add User",
				role: "user",
				styleClass: "btn-add-user",
				gen: false,
			},
			addSystem: {
				text: "Add System",
				role: "system",
				styleClass: "btn-add-system",
				gen: false,
			},
			addAssistant: {
				text: "Add Assistant",
				role: "assistant",
				styleClass: "btn-add-assistant",
				gen: false,
			},
			genAssistant: {
				text: "Gen Assistant",
				role: null,
				styleClass: "btn-gen-assistant",
				gen: true,
			},
		};

		let primaryAction, dropdownActions;

		if (lastMessageIsUser) {
			primaryAction = actions.genAssistant;
			dropdownActions = [
				actions.addUser,
				actions.addSystem,
				actions.addAssistant,
			];
		} else {
			// No messages, or last message was from system/assistant
			primaryAction = actions.addUser;
			dropdownActions = [
				actions.genAssistant,
				actions.addSystem,
				actions.addAssistant,
			];
		}

		// Configure Primary Button
		primaryBtn.textContent = primaryAction.text;
		primaryBtn.className = primaryAction.styleClass; // Set class for styling

		if (primaryBtn.clickHandler) {
			primaryBtn.removeEventListener("click", primaryBtn.clickHandler);
		}
		primaryBtn.clickHandler = createActionHandler(primaryAction);
		primaryBtn.addEventListener("click", primaryBtn.clickHandler);

		// Populate Dropdown Menu
		dropdownMenu.innerHTML = "";
		dropdownActions.forEach((action) => {
			const button = document.createElement("button");
			button.textContent = action.text;
			// Note: dropdown items don't get special color classes, styled as menu items
			button.addEventListener("click", createActionHandler(action));
			dropdownMenu.appendChild(button);
			allButtons.push(button);
		});
	}

	function setButtonsDisabledState(buttons, disabled) {
		buttons.forEach((btn) => {
			if (btn) btn.disabled = disabled;
		});
	}

	// Helper function to update the state of global action buttons (Add User, System, etc.)
	function updateGlobalActionButtonsState() {
		const isAnyMessageEditing = !!document.querySelector(
			".message[data-editing='true']",
		);

		const messageButtons = document.querySelectorAll("#message-buttons button");
		messageButtons.forEach((button) => {
			if (button) {
				button.disabled = isAnyMessageEditing;
			}
		});
	}

	function jumpToLatestMessage() {
		const messagesContainerElem = document.getElementById("messages-container");
		if (messagesContainerElem) {
			const messageElements =
				messagesContainerElem.querySelectorAll(".message");
			if (messageElements.length > 0) {
				const lastMessageElement = messageElements[messageElements.length - 1];
				lastMessageElement.scrollIntoView({ behavior: "smooth", block: "end" });
			} else {
				// If no messages, scroll to the bottom of the (empty) messages container
				messagesContainerElem.scrollIntoView({
					behavior: "smooth",
					block: "end",
				});
			}
		}
	}

	// Helper to create action buttons for individual messages (Edit, Archive, Save, Cancel)
	function createActionButton(svgIconHtml, className, onClick) {
		const button = document.createElement("button");
		button.type = "button";
		button.innerHTML = svgIconHtml; // Use innerHTML for SVG icons
		button.className = className; // Add class for styling
		button.addEventListener("click", onClick);
		return button;
	}

	function toggleEditState(
		messageElement,
		contentWrapperDiv,
		actionsDiv,
		originalContent,
		conversationId,
		filename,
		reasoning = null,
	) {
		const isEditing = messageElement.dataset.editing === "true";

		if (isEditing) {
			// ---- Switching from Edit to View (Cancel or Save) ----
			// Note: originalContent is passed as argument, could be the newly saved content
			contentWrapperDiv.innerHTML = ""; // Clear textarea
			contentWrapperDiv.textContent = originalContent; // Restore/set content

			actionsDiv.innerHTML = ""; // Clear Save/Cancel buttons

			const infoButton = createActionButton(ICON_INFO, "btn-info", () =>
				showMessageInfoModal(filename, originalContent),
			);
			infoButton.title = "Info";

			const editButton = createActionButton(ICON_PENCIL, "btn-edit", () =>
				toggleEditState(
					messageElement,
					contentWrapperDiv,
					actionsDiv,
					originalContent, // This is now the current content
					conversationId,
					filename,
					reasoning,
				),
			);
			editButton.title = "Edit";

			const archiveButton = createActionButton(
				ICON_ARCHIVE,
				"btn-archive",
				() =>
					handleArchiveMessage(
						messageElement,
						conversationId,
						filename,
						reasoning,
					),
			);
			archiveButton.title = "Archive";

			actionsDiv.appendChild(infoButton);
			actionsDiv.appendChild(editButton);
			actionsDiv.appendChild(archiveButton);

			delete messageElement.dataset.editing;
			delete messageElement.dataset.originalContentForEdit; // Clean up
			updateGlobalActionButtonsState(); // Update global buttons state
		} else {
			// ---- Switching from View to Edit ----
			messageElement.dataset.editing = "true";
			// Store original content on the element in case of cancel
			messageElement.dataset.originalContentForEdit = originalContent;

			contentWrapperDiv.innerHTML = ""; // Clear current text content
			const textarea = document.createElement("textarea");
			textarea.value = originalContent;
			// autoresize textarea
			textarea.style.height = "auto"; // Temporarily set to auto to get scrollHeight
			textarea.style.height = `${textarea.scrollHeight}px`;
			textarea.addEventListener("input", () => {
				// Adjust height on input
				textarea.style.height = "auto";
				textarea.style.height = `${textarea.scrollHeight}px`;
			});
			contentWrapperDiv.appendChild(textarea);
			textarea.focus();

			actionsDiv.innerHTML = ""; // Clear Edit/Archive buttons
			const saveButton = createActionButton(ICON_SAVE, "btn-save", () =>
				handleSaveMessage(
					messageElement,
					contentWrapperDiv,
					actionsDiv,
					textarea, // Pass textarea to get its current value
					conversationId,
					filename,
					reasoning,
				),
			);
			saveButton.title = "Save";

			const cancelButton = createActionButton(ICON_X, "btn-cancel", () =>
				// Revert to view mode with the stored original content
				toggleEditState(
					messageElement,
					contentWrapperDiv,
					actionsDiv,
					messageElement.dataset.originalContentForEdit, // Use stored original
					conversationId,
					filename,
					reasoning,
				),
			);
			cancelButton.title = "Cancel";

			actionsDiv.appendChild(saveButton);
			actionsDiv.appendChild(cancelButton);
			updateGlobalActionButtonsState(); // Update global buttons state
		}
	}

	async function handleArchiveMessage(
		messageElement,
		conversationId,
		filename,
		reasoning = null,
	) {
		// Clear previous errors specifically for this message's actions
		if (messageElement) {
			clearErrorMessages(
				messageElement.querySelector(".message-actions") || messageElement,
			);
		}

		try {
			// Archive the main message
			const response = await authFetch(
				`/api/conversation/${encodeURIComponent(conversationId)}/message/${encodeURIComponent(filename)}/archive`,
				{
					method: "POST",
				},
			);

			if (!response.ok) {
				const errorData = await response
					.json()
					.catch(() => ({ detail: "Failed to archive message." }));
				throw new Error(errorData.detail || `HTTP error ${response.status}`);
			}

			// If there's associated reasoning, archive it too
			if (reasoning && reasoning.filename) {
				try {
					const reasoningResponse = await authFetch(
						`/api/conversation/${encodeURIComponent(conversationId)}/message/${encodeURIComponent(reasoning.filename)}/archive`,
						{
							method: "POST",
						},
					);

					if (!reasoningResponse.ok) {
						console.error(
							"Failed to archive reasoning message, but main message was archived",
						);
					}
				} catch (reasoningError) {
					console.error("Error archiving reasoning message:", reasoningError);
					// Don't fail the whole operation if reasoning archive fails
				}
			}

			// On success, remove the message element from the DOM
			messageElement.remove();
			updateSplitButtonState(conversationId);
			updateGlobalActionButtonsState(); // Check if this removal affects global buttons state
			jumpToLatestMessage(); // Scroll to the latest message after archiving one

			// No need to reload full conversation, message is gone from this view.
			// It will appear in "Other Files" on next full load/refresh.
			// To refresh "Other Files" immediately, one could call loadConversationDetails(conversationId)
			// but that's a full reload. For now, let it update on page refresh.
		} catch (error) {
			console.error("Error archiving message:", error);
			handleError(
				`Error archiving message: ${error.message}`,
				messageElement.querySelector(".message-actions") || messageElement,
			);
		}
	}

	async function handleSaveMessage(
		messageElement,
		contentWrapperDiv,
		actionsDiv,
		textareaElement,
		conversationId,
		filename,
		reasoning = null,
	) {
		const newContent = textareaElement.value;

		// Clear previous errors from actions area
		clearErrorMessages(actionsDiv);

		// Disable Save/Cancel temporarily
		const saveCancelButtons = actionsDiv.querySelectorAll("button");
		setButtonsDisabledState(Array.from(saveCancelButtons), true);

		try {
			const response = await authFetch(
				`/api/conversation/${encodeURIComponent(conversationId)}/message/${encodeURIComponent(filename)}/edit`,
				{
					method: "PUT",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({ content: newContent }),
				},
			);

			if (!response.ok) {
				const errorData = await response
					.json()
					.catch(() => ({ detail: "Failed to save message." }));
				throw new Error(errorData.detail || `HTTP error ${response.status}`);
			}

			// const responseData = await response.json(); // Contains new_content, archived_as
			// Successfully saved. Update UI to view mode with new content.
			// The newContent is now the "original" content for future edits.
			toggleEditState(
				messageElement,
				contentWrapperDiv,
				actionsDiv,
				newContent, // Pass the new content to be displayed and set as original
				conversationId,
				filename,
				reasoning,
			);
		} catch (error) {
			console.error("Error saving message:", error);
			handleError(`Error saving message: ${error.message}`, actionsDiv);
			// Re-enable Save/Cancel buttons on error
			setButtonsDisabledState(Array.from(saveCancelButtons), false);
		}
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

		const headerDiv = document.createElement("div");
		headerDiv.className = "message-header";
		const roleSpan = document.createElement("span");
		roleSpan.className = "message-role";
		roleSpan.textContent = "Assistant";
		const filenameSpan = document.createElement("span");
		filenameSpan.className = "message-filename";
		filenameSpan.textContent = " - Generating..."; // Placeholder text with separator
		headerDiv.appendChild(roleSpan);
		headerDiv.appendChild(filenameSpan);

		const contentWrapperDiv = document.createElement("div");
		contentWrapperDiv.className = "message-content-wrapper";
		// contentWrapperDiv.style.whiteSpace = "pre-wrap"; // Ensure pre-wrap for streaming

		// Create reasoning container (will be populated if reasoning content arrives)
		let reasoningContainer = null;
		let reasoningContent = null;
		let reasoningHeader = null;
		let toggleIcon = null;

		placeholderDiv.appendChild(headerDiv);
		// Reasoning container will be inserted here when needed
		placeholderDiv.appendChild(contentWrapperDiv);
		messagesContainer.appendChild(placeholderDiv);
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
										reasoningContainer.className =
											"message-reasoning-container";
										reasoningContainer.style.margin = "10px 0";

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
											const isVisible =
												reasoningContent.style.display !== "none";
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
									if (!reasoningContent.textContent) {
										reasoningContent.textContent = reasoningText;
									} else {
										reasoningContent.textContent += reasoningText;
									}
								} else {
									contentWrapperDiv.textContent += data;
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
								reasoningContainer.style.margin = "10px 0";

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
							reasoningContent.textContent += reasoningText;
						} else {
							contentWrapperDiv.textContent += data;
						}
					}
				} else {
					contentWrapperDiv.textContent += buffer;
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
			filenameSpan.textContent = "Error";
			contentWrapperDiv.textContent = `Error during generation: ${escapeHtml(error.message)}`;
			// Do not re-enable buttons here, `finally` block below calls loadConversationDetails
			// which will fully reconstruct the input area.
			// If loadConversationDetails is skipped on error, then buttons should be re-enabled.
			// However, the design is to always try to load details.
		} finally {
			// Regardless of success or failure of the stream, reload the conversation details
			// to get the final state from the server (new messages, files, etc.)
			// This will also remove the placeholder and re-enable buttons correctly.
			loadConversationDetails(conversationId);
		}
	}

	async function updateConversationTitle(
		conversationId,
		newTitle,
		inputElement,
	) {
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
			inputElement.style.borderColor = "#81ae9d"; // New: green
			setTimeout(() => {
				inputElement.style.borderColor = "";
			}, 1500);

			inputElement.value = escapeHtml(savedTitle === "-" ? "" : savedTitle);
			inputElement.dataset.originalTitle = savedTitle;
			console.log(`Title for ${conversationId} updated to "${savedTitle}"`);
		} catch (error) {
			console.error("Failed to update title:", error);
			handleError(
				`Error updating title: ${error.message}`,
				inputElement.parentElement,
			);
			throw error; // Re-throw to allow caller to handle UI revert
		}
	}

	async function updateConversationModel(
		conversationId,
		newModel,
		inputElement,
	) {
		clearErrorMessages(
			inputElement.closest(".model-edit-container") ||
				inputElement.parentElement,
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

			inputElement.style.borderColor = "#81ae9d"; // New: green
			setTimeout(() => {
				inputElement.style.borderColor = "";
			}, 1500);

			inputElement.value = escapeHtml(savedModel); // Update input to what was actually saved
			inputElement.dataset.originalModel = savedModel;
			console.log(`Model for ${conversationId} updated to "${savedModel}"`);
		} catch (error) {
			console.error("Failed to update model:", error);
			handleError(
				`Error updating model: ${error.message}`,
				inputElement.parentElement,
			);
			throw error; // Re-throw to allow caller to handle UI revert
		}
	}

	function clearErrorMessages(container) {
		if (!container) return;
		const errorMessages = container.querySelectorAll(".error-message");
		errorMessages.forEach((msg) => msg.remove());
	}

	function handleError(message, contextElement) {
		// If contextElement is provided, try to place the error message near it.
		// Otherwise, use a general container.
		let targetContainer;
		if (contextElement) {
			// If it's an input, place error after its parent (li) or the input itself
			// Also handle if contextElement is the button itself, place error near its parent or button
			if (
				(contextElement.tagName === "INPUT" ||
					contextElement.tagName === "BUTTON") &&
				contextElement.parentElement
			) {
				targetContainer = contextElement.parentElement;
			} else {
				targetContainer = contextElement;
			}
		} else {
			targetContainer =
				document.getElementById("conversation-list-container") ||
				document.getElementById("messages-container") || // For conversation detail page
				document.body;
		}

		// Remove existing error messages within this specific context if possible
		// Ensure clearErrorMessages is robust if targetContainer doesn't have querySelectorAll (e.g. text node)
		if (
			targetContainer &&
			typeof targetContainer.querySelectorAll === "function"
		) {
			if (targetContainer !== document.body) {
				// Avoid clearing all errors if falling back to body
				clearErrorMessages(targetContainer);
			}
		}

		const errorP = document.createElement("p");
		errorP.className = "error-message";
		errorP.textContent = escapeHtml(message);

		if (targetContainer && targetContainer.tagName === "LI") {
			// Specific for conversation list items
			targetContainer.appendChild(errorP); // Add error message within the li
		} else if (
			targetContainer &&
			targetContainer.firstChild &&
			targetContainer.firstChild.nodeName === "H1"
		) {
			targetContainer.firstChild.insertAdjacentElement("afterend", errorP);
		} else if (targetContainer) {
			targetContainer.prepend(errorP); // General placement
		} else {
			// Fallback if targetContainer is null for some reason
			document.body.appendChild(errorP);
		}
	}

	function showMessageInfoModal(filename, content) {
		const lineCount = content.split("\n").length;
		const charCount = content.length;

		const overlay = document.createElement("div");
		overlay.className = "info-modal-overlay";

		const modalContent = document.createElement("div");
		modalContent.className = "info-modal-content";

		modalContent.innerHTML = `
			<p><strong>File:</strong> ${escapeHtml(filename)}</p>
			<p><strong>Lines:</strong> ${lineCount}</p>
			<p><strong>Characters:</strong> ${charCount}</p>
		`;

		const closeButton = document.createElement("button");
		closeButton.className = "info-modal-close";
		closeButton.innerHTML = ICON_X;

		const closeModal = () => {
			overlay.remove();
		};

		closeButton.addEventListener("click", closeModal);
		overlay.addEventListener("click", (e) => {
			// Close if clicked on the overlay itself, not the content
			if (e.target === overlay) {
				closeModal();
			}
		});

		modalContent.appendChild(closeButton);
		overlay.appendChild(modalContent);
		document.body.appendChild(overlay);
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
				buttonElement.textContent = responseData.is_pinned ? "Unpin" : "Pin";
			}
			// Optionally, provide a success message, though button text change is often enough.
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

	async function showShareModal(conversationId) {
		const overlay = document.createElement("div");
		overlay.className = "share-modal-overlay";

		const modalContent = document.createElement("div");
		modalContent.className = "share-modal-content";

		modalContent.innerHTML = `
			<h2>Share Conversation</h2>
			<div id="share-error" class="error-message" style="display: none;"></div>
			<div id="current-users">
				<h3>Current Users with Access:</h3>
				<p>Loading...</p>
			</div>
			<div class="share-form">
				<h3>Add Users:</h3>
				<input type="text" id="share-users-input" placeholder="Enter usernames separated by commas">
				<div class="share-modal-buttons">
					<button type="button" id="share-save-btn" class="btn-primary">Update Access</button>
					<button type="button" id="share-cancel-btn" class="btn-secondary">Cancel</button>
				</div>
			</div>
		`;

		const closeModal = () => {
			overlay.remove();
		};

		overlay.appendChild(modalContent);
		document.body.appendChild(overlay);

		// Load current access list
		try {
			const response = await authFetch(
				`/api/conversation/${encodeURIComponent(conversationId)}/access`,
			);
			if (response.ok) {
				const data = await response.json();
				const currentUsersDiv = document.getElementById("current-users");
				if (data.users && data.users.length > 0) {
					currentUsersDiv.innerHTML = `
						<h3>Current Users with Access:</h3>
						<ul>${data.users.map((u) => `<li>${escapeHtml(u)}</li>`).join("")}</ul>
					`;
					// Pre-fill the input with current users
					document.getElementById("share-users-input").value =
						data.users.join(", ");
				}
			}
		} catch (error) {
			console.error("Error loading access list:", error);
		}

		// Setup buttons
		document
			.getElementById("share-cancel-btn")
			.addEventListener("click", closeModal);
		overlay.addEventListener("click", (e) => {
			if (e.target === overlay) closeModal();
		});

		document
			.getElementById("share-save-btn")
			.addEventListener("click", async () => {
				const input = document.getElementById("share-users-input");
				const errorDiv = document.getElementById("share-error");
				const saveBtn = document.getElementById("share-save-btn");

				const usersText = input.value.trim();
				if (!usersText) {
					errorDiv.textContent = "Please enter at least one username";
					errorDiv.style.display = "block";
					return;
				}

				const users = usersText
					.split(",")
					.map((u) => u.trim())
					.filter((u) => u);

				saveBtn.disabled = true;
				errorDiv.style.display = "none";

				try {
					const response = await authFetch(
						`/api/conversation/${encodeURIComponent(conversationId)}/share`,
						{
							method: "POST",
							headers: { "Content-Type": "application/json" },
							body: JSON.stringify({ users }),
						},
					);

					if (response.ok) {
						const data = await response.json();
						// Update the display
						const currentUsersDiv = document.getElementById("current-users");
						if (data.users && data.users.length > 0) {
							currentUsersDiv.innerHTML = `
							<h3>Current Users with Access:</h3>
							<ul>${data.users.map((u) => `<li>${escapeHtml(u)}</li>`).join("")}</ul>
						`;
						}
						// Success feedback
						errorDiv.textContent = "Access updated successfully!";
						errorDiv.style.display = "block";
						errorDiv.style.backgroundColor = "#204a20";
						errorDiv.style.color = "#6bff6b";
						setTimeout(closeModal, 1500);
					} else {
						throw new Error("Failed to update access");
					}
				} catch (error) {
					errorDiv.textContent = `Error: ${error.message}`;
					errorDiv.style.display = "block";
					saveBtn.disabled = false;
				}
			});
	}
});
