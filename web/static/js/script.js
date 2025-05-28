document.addEventListener("DOMContentLoaded", () => {
	const DEFAULT_MODEL_NAME = "openrouter/deepseek/deepseek-chat-v3-0324:free";

	const path = window.location.pathname;

	if (path === "/") {
		loadConversationsList();
		const createBtn = document.getElementById("create-conversation-btn");
		if (createBtn) {
			createBtn.addEventListener("click", handleCreateConversation);
		}
	} else if (path.startsWith("/conversation-page/")) {
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
			const response = await fetch("/api/conversations");
			if (!response.ok) {
				throw new Error(`HTTP error! status: ${response.status}`);
			}
			const data = await response.json(); // Expects { conversations: [{id: "...", title: "...", is_pinned: bool}, ...] }

			if (data.conversations && data.conversations.length > 0) {
				const ul = document.createElement("ul");
				data.conversations.forEach((conv) => {
					const li = document.createElement("li");
					if (conv.is_pinned) {
						li.classList.add("pinned-conversation");
					}

					const a = document.createElement("a");
					a.href = `/conversation-page/${encodeURIComponent(conv.id)}`;
					a.textContent = escapeHtml(conv.id);
					li.appendChild(a);

					const titleSpan = document.createElement("span");
					titleSpan.className = "conversation-list-title";
					let displayTitle = escapeHtml(conv.title).trim();
					if (!displayTitle) {
						displayTitle = "-";
					}
					let titleContent = ` - ${displayTitle}`;
					if (conv.is_pinned) {
						titleContent += ` <span class="pin-emoji">📌</span>`;
					}
					titleSpan.innerHTML = titleContent; // Use innerHTML for the emoji span
					li.appendChild(titleSpan);

					ul.appendChild(li);
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
			const response = await fetch("/api/conversations/create", {
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
				window.location.href = `/conversation-page/${encodeURIComponent(responseData.conversation_id)}`;
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
		const messagesContainer = document.getElementById("messages-container");
		const otherFilesContainer = document.getElementById(
			"other-files-container",
		);

		const safeConvId = escapeHtml(conversationId);

		// Initial state for inputs and buttons
		document.title = `Loading: ${safeConvId}`;
		mainTitleDisplayElement.textContent = `Loading conversation: ${safeConvId}...`;
		titleEditInput.value = "";
		titleEditInput.disabled = true;
		modelEditInput.value = "";
		modelEditInput.disabled = true;
		if (pinToggleButton) {
			pinToggleButton.disabled = true;
			pinToggleButton.textContent = "Pin"; // Default before loading
		}

		try {
			const response = await fetch(
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
						? `${escapeHtml(currentTitle)} (${safeConvId})`
						: `Conversation: ${safeConvId}`;
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
				data.messages.forEach((msg) => {
					const messageDiv = document.createElement("div");
					messageDiv.className = `message message-${escapeHtml(msg.role.toLowerCase())}`;
					messageDiv.dataset.filename = msg.filename; // Store filename for actions

					const headerDiv = document.createElement("div");
					headerDiv.className = "message-header";

					const roleSpan = document.createElement("span");
					roleSpan.className = "message-role";
					roleSpan.textContent = escapeHtml(msg.role);

					const filenameSpan = document.createElement("span");
					filenameSpan.className = "message-filename";
					filenameSpan.textContent = escapeHtml(msg.filename);

					headerDiv.appendChild(roleSpan);
					headerDiv.appendChild(filenameSpan);

					// Wrapper for content to allow easy replacement (text <-> textarea)
					const contentWrapperDiv = document.createElement("div");
					contentWrapperDiv.className = "message-content-wrapper";
					contentWrapperDiv.textContent = msg.content; // Initial content display

					// Actions (Edit, Archive)
					const actionsDiv = document.createElement("div");
					actionsDiv.className = "message-actions";

					const editButton = createActionButton("✏️", "btn-edit", () =>
						// Emoji: Pencil
						toggleEditState(
							messageDiv,
							contentWrapperDiv,
							actionsDiv,
							msg.content,
							conversationId,
							msg.filename,
						),
					);
					editButton.title = "Edit"; // Tooltip for accessibility

					const archiveButton = createActionButton(
						"🗑️", // Emoji: Trash can
						"btn-archive",
						() =>
							handleArchiveMessage(messageDiv, conversationId, msg.filename),
					);
					archiveButton.title = "Archive"; // Tooltip for accessibility

					actionsDiv.appendChild(editButton);
					actionsDiv.appendChild(archiveButton);

					messageDiv.appendChild(headerDiv);
					messageDiv.appendChild(contentWrapperDiv);
					messageDiv.appendChild(actionsDiv);
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
				const heading = document.createElement("h2");
				heading.textContent = "Other Files";
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
				otherFilesContainer.appendChild(divider);
				otherFilesContainer.appendChild(heading);
				otherFilesContainer.appendChild(ul);
			}

			// After rendering messages and other files, set up the input area
			setupMessageInputArea(conversationId);

			// Setup Fork button listener
			const forkButton = document.getElementById("fork-conversation-btn");
			if (forkButton) {
				forkButton.addEventListener("click", () => {
					handleForkConversation(conversationId);
				});
			} else {
				console.warn("Fork button (#fork-conversation-btn) not found in DOM.");
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

		// References to all buttons for easy disabling/enabling
		const allButtons = [];

		const btnAddUser = createButton("btn-add-user", "Add User", () =>
			handleAddMessage(conversationId, "user", textarea, allButtons),
		);
		allButtons.push(btnAddUser);

		const btnAddSystem = createButton("btn-add-system", "Add System", () =>
			handleAddMessage(conversationId, "system", textarea, allButtons),
		);
		allButtons.push(btnAddSystem);

		const btnAddAssistant = createButton(
			"btn-add-assistant",
			"Add Assistant",
			() => handleAddMessage(conversationId, "assistant", textarea, allButtons),
		);
		allButtons.push(btnAddAssistant);

		const btnGenAssistant = createButton(
			"btn-gen-assistant",
			"Gen Assistant",
			() => handleGenAssistant(conversationId, allButtons),
		);
		allButtons.push(btnGenAssistant);

		buttonsDiv.appendChild(btnAddUser);
		buttonsDiv.appendChild(btnAddSystem);
		buttonsDiv.appendChild(btnAddAssistant);
		buttonsDiv.appendChild(btnGenAssistant);

		messageInputArea.appendChild(textarea);
		messageInputArea.appendChild(buttonsDiv);

		// Append the whole message input area
		const mainPageContainer = document.querySelector("div.container");
		const otherFilesDiv = document.getElementById("other-files-container");

		if (mainPageContainer) {
			if (otherFilesDiv) {
				// Insert the message input area before the "Other Files" container
				mainPageContainer.insertBefore(messageInputArea, otherFilesDiv);
			} else {
				// Fallback: if other-files-container is not found, append to main container.
				console.warn(
					"#other-files-container not found, appending message input to end of main container.",
				);
				mainPageContainer.appendChild(messageInputArea);
			}
			adjustTextareaHeightOnInput(textarea); // Initial height adjustment
		} else {
			console.error(
				"Could not find '.container' to append message input area.",
			);
			document.body.appendChild(messageInputArea); // Fallback
			adjustTextareaHeightOnInput(textarea); // Initial height adjustment
		}
	}

	// Helper to create main action buttons (Add User, System, etc.)
	function createButton(id, text, onClick) {
		const button = document.createElement("button");
		button.id = id;
		button.type = "button";
		button.textContent = text;
		button.addEventListener("click", onClick);
		return button;
	}

	function setButtonsDisabledState(buttons, disabled) {
		buttons.forEach((btn) => {
			if (btn) btn.disabled = disabled;
		});
	}

	// Helper to create action buttons for individual messages (Edit, Archive, Save, Cancel)
	function createActionButton(text, className, onClick) {
		const button = document.createElement("button");
		button.type = "button";
		button.textContent = text;
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
	) {
		const isEditing = messageElement.dataset.editing === "true";

		if (isEditing) {
			// ---- Switching from Edit to View (Cancel or Save) ----
			// Note: originalContent is passed as argument, could be the newly saved content
			contentWrapperDiv.innerHTML = ""; // Clear textarea
			contentWrapperDiv.textContent = originalContent; // Restore/set content

			actionsDiv.innerHTML = ""; // Clear Save/Cancel buttons
			const editButton = createActionButton("✏️", "btn-edit", () =>
				// Emoji: Pencil
				toggleEditState(
					messageElement,
					contentWrapperDiv,
					actionsDiv,
					originalContent, // This is now the current content
					conversationId,
					filename,
				),
			);
			editButton.title = "Edit";

			const archiveButton = createActionButton("🗑️", "btn-archive", () =>
				// Emoji: Trash can
				handleArchiveMessage(messageElement, conversationId, filename),
			);
			archiveButton.title = "Archive";

			actionsDiv.appendChild(editButton);
			actionsDiv.appendChild(archiveButton);

			delete messageElement.dataset.editing;
			delete messageElement.dataset.originalContentForEdit; // Clean up
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
			const saveButton = createActionButton("💾", "btn-save", () =>
				// Emoji: Floppy Disk (Save)
				handleSaveMessage(
					messageElement,
					contentWrapperDiv,
					actionsDiv,
					textarea, // Pass textarea to get its current value
					conversationId,
					filename,
				),
			);
			saveButton.title = "Save";

			const cancelButton = createActionButton("❌", "btn-cancel", () =>
				// Emoji: Cross Mark (Cancel)
				// Revert to view mode with the stored original content
				toggleEditState(
					messageElement,
					contentWrapperDiv,
					actionsDiv,
					messageElement.dataset.originalContentForEdit, // Use stored original
					conversationId,
					filename,
				),
			);
			cancelButton.title = "Cancel";

			actionsDiv.appendChild(saveButton);
			actionsDiv.appendChild(cancelButton);
		}
	}

	async function handleArchiveMessage(
		messageElement,
		conversationId,
		filename,
	) {
		// Clear previous errors specifically for this message's actions
		if (messageElement) {
			clearErrorMessages(
				messageElement.querySelector(".message-actions") || messageElement,
			);
		}

		try {
			const response = await fetch(
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

			// On success, remove the message element from the DOM
			messageElement.remove();
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
	) {
		const newContent = textareaElement.value;

		// Clear previous errors from actions area
		clearErrorMessages(actionsDiv);

		// Disable Save/Cancel temporarily
		const saveCancelButtons = actionsDiv.querySelectorAll("button");
		setButtonsDisabledState(Array.from(saveCancelButtons), true);

		try {
			const response = await fetch(
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
			const response = await fetch(
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
		filenameSpan.textContent = "Generating..."; // Placeholder text
		headerDiv.appendChild(roleSpan);
		headerDiv.appendChild(filenameSpan);

		const contentWrapperDiv = document.createElement("div");
		contentWrapperDiv.className = "message-content-wrapper";
		// contentWrapperDiv.style.whiteSpace = "pre-wrap"; // Ensure pre-wrap for streaming

		placeholderDiv.appendChild(headerDiv);
		placeholderDiv.appendChild(contentWrapperDiv);
		messagesContainer.appendChild(placeholderDiv);
		// Removed: placeholderDiv.scrollIntoView({ behavior: "smooth", block: "end" });

		try {
			const response = await fetch(
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
			while (!done) {
				const { value, done: readerDone } = await reader.read();
				done = readerDone;
				if (value) {
					const chunk = decoder.decode(value, { stream: !done });
					contentWrapperDiv.textContent += chunk;
					// Removed: placeholderDiv.scrollIntoView({ block: "end" });
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
			const response = await fetch(
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
			const savedTitle = responseData.new_title;

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
			const response = await fetch(
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
			const savedModel = responseData.new_model; // Backend returns actual saved model (e.g. default)

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

	async function handlePinToggle(conversationId, buttonElement) {
		if (buttonElement) buttonElement.disabled = true;
		const titleSection = document.querySelector(".title-section");
		if (titleSection) clearErrorMessages(titleSection);

		try {
			const response = await fetch(
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

			const responseData = await response.json(); // Expects {"pinned": boolean, "message": "..."}
			if (buttonElement) {
				buttonElement.textContent = responseData.pinned ? "Unpin" : "Pin";
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
			const response = await fetch(
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
			if (responseData && responseData.new_conversation_id) {
				window.location.href = `/conversation-page/${encodeURIComponent(responseData.new_conversation_id)}`;
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
});
