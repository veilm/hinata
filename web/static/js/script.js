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
			const data = await response.json(); // Expects { conversations: [{id: "...", title: "..."}, ...] }

			if (data.conversations && data.conversations.length > 0) {
				const ul = document.createElement("ul");
				data.conversations.forEach((conv) => {
					const li = document.createElement("li");

					const a = document.createElement("a");
					a.href = `/conversation-page/${encodeURIComponent(conv.id)}`;
					a.textContent = escapeHtml(conv.id);
					li.appendChild(a);

					const titleSpan = document.createElement("span");
					titleSpan.className = "conversation-list-title";
					// Display title read-only. Default to "-" if title is empty, null, or just whitespace.
					let displayTitle = escapeHtml(conv.title).trim();
					if (!displayTitle) {
						displayTitle = "-";
					}
					titleSpan.textContent = ` - ${displayTitle}`;
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

			// Success! Reload the page to see the new conversation in the list.
			window.location.reload();
		} catch (error) {
			console.error("Error creating conversation:", error);
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
		const modelEditInput = document.getElementById("conversation-model-input"); // New model input
		const messagesContainer = document.getElementById("messages-container");
		const otherFilesContainer = document.getElementById(
			"other-files-container",
		);

		const safeConvId = escapeHtml(conversationId);

		// Initial title before fetching full data
		document.title = `Loading: ${safeConvId}`;
		mainTitleDisplayElement.textContent = `Loading conversation: ${safeConvId}...`;
		titleEditInput.value = ""; // Clear initially
		titleEditInput.disabled = true; // Disable until data loaded
		modelEditInput.value = ""; // Clear initially
		modelEditInput.disabled = true; // Disable until data loaded

		try {
			const response = await fetch(
				`/api/conversation/${encodeURIComponent(conversationId)}`,
			);
			if (!response.ok) {
				throw new Error(`HTTP error! status: ${response.status}`);
			}
			const data = await response.json(); // Expects { conversation_id, title, model, messages, other_files }

			// --- Title Handling ---
			const convTitle = data.title || "-"; // Default to "-" if title is null/undefined/empty
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

			// Render messages
			messagesContainer.innerHTML = ""; // Clear potential loading/error states
			if (data.messages && data.messages.length > 0) {
				data.messages.forEach((msg) => {
					const messageDiv = document.createElement("div");
					messageDiv.className = `message message-${escapeHtml(msg.role.toLowerCase())}`;

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

					const contentDiv = document.createElement("div");
					// Content is pre-wrap, so textContent is fine.
					// If content could contain HTML that needs to be rendered as HTML this would be different.
					contentDiv.textContent = msg.content;

					messageDiv.appendChild(headerDiv);
					messageDiv.appendChild(contentDiv);
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
		} catch (error) {
			handleError(
				`Failed to load conversation: ${safeConvId}.`,
				messagesContainer,
			);
			console.error(`Error loading conversation ${conversationId}:`, error);
			otherFilesContainer.innerHTML = ""; // Clear other files section on error too
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
			if (contextElement.tagName === "INPUT" && contextElement.parentElement) {
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
		if (targetContainer !== document.body) {
			// Avoid clearing all errors if falling back to body
			clearErrorMessages(targetContainer);
		}

		const errorP = document.createElement("p");
		errorP.className = "error-message";
		errorP.textContent = escapeHtml(message);

		if (targetContainer.tagName === "LI") {
			// Specific for conversation list items
			targetContainer.appendChild(errorP); // Add error message within the li
		} else if (
			targetContainer.firstChild &&
			targetContainer.firstChild.nodeName === "H1"
		) {
			targetContainer.firstChild.insertAdjacentElement("afterend", errorP);
		} else {
			targetContainer.prepend(errorP); // General placement
		}
	}
});
