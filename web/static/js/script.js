document.addEventListener("DOMContentLoaded", () => {
	const path = window.location.pathname;

	if (path === "/") {
		loadConversationsList();
	} else if (path.startsWith("/conversation-page/")) {
		const parts = path.split("/");
		const conversationId = parts[parts.length - 1];
		if (conversationId) {
			loadConversationDetails(conversationId);
		} else {
			handleError("Conversation ID missing in URL.");
		}
	}
});

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

async function loadConversationDetails(conversationId) {
	const mainTitleDisplayElement = document.getElementById(
		"conversation-id-display",
	);
	const titleEditInput = document.getElementById("conversation-title-input");
	const messagesContainer = document.getElementById("messages-container");
	const otherFilesContainer = document.getElementById("other-files-container");

	const safeConvId = escapeHtml(conversationId);

	// Initial title before fetching full data
	document.title = `Loading: ${safeConvId}`;
	mainTitleDisplayElement.textContent = `Loading conversation: ${safeConvId}...`;
	titleEditInput.value = ""; // Clear initially
	titleEditInput.disabled = true; // Disable until data loaded

	try {
		const response = await fetch(
			`/api/conversation/${encodeURIComponent(conversationId)}`,
		);
		if (!response.ok) {
			throw new Error(`HTTP error! status: ${response.status}`);
		}
		const data = await response.json(); // Expects { conversation_id, title, messages, other_files }

		const convTitle = data.title || "-"; // Default to "-" if title is null/undefined/empty

		// Update page title, heading, and input field with fetched title
		const updateDisplayedTitle = (currentTitle) => {
			const displayPageTitle =
				currentTitle && currentTitle !== "-"
					? `${escapeHtml(currentTitle)} (${safeConvId})`
					: `Conversation: ${safeConvId}`;
			document.title = displayPageTitle;
			mainTitleDisplayElement.textContent = displayPageTitle;
		};

		updateDisplayedTitle(convTitle);
		titleEditInput.value = escapeHtml(convTitle === "-" ? "" : convTitle); // Show empty if "-", for better editing UX
		titleEditInput.dataset.originalTitle = convTitle; // Store original title (could be "-")
		titleEditInput.disabled = false;

		// Event listener for title input blur (lost focus)
		titleEditInput.addEventListener("blur", async () => {
			let newTitle = titleEditInput.value.trim();
			const originalTitle = titleEditInput.dataset.originalTitle;

			if (newTitle === "") {
				newTitle = "-"; // Default to "-" if input is cleared
			}

			if (newTitle !== originalTitle) {
				try {
					// Pass titleEditInput as the element for UI feedback/error context
					await updateConversationTitle(
						conversationId,
						newTitle,
						titleEditInput,
					);
					titleEditInput.dataset.originalTitle = newTitle; // Update stored original title on success
					// Reflect the possibly changed newTitle (e.g., if empty became "-")
					titleEditInput.value = escapeHtml(newTitle === "-" ? "" : newTitle);
					updateDisplayedTitle(newTitle); // Update the H1 and document title
				} catch (error) {
					// Error handled by updateConversationTitle, revert input UI
					titleEditInput.value = escapeHtml(
						originalTitle === "-" ? "" : originalTitle,
					);
				}
			} else if (titleEditInput.value.trim() !== newTitle && newTitle === "-") {
				// Case: input was spaces, now should show empty (representing "-")
				titleEditInput.value = "";
			}
		});

		// Event listener for Enter key in title input
		titleEditInput.addEventListener("keypress", (event) => {
			if (event.key === "Enter") {
				titleEditInput.blur(); // Trigger blur to save
			}
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

async function updateConversationTitle(conversationId, newTitle, inputElement) {
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

		// Visually indicate success briefly (optional)
		inputElement.style.borderColor = "#98c379"; // Green
		setTimeout(() => {
			inputElement.style.borderColor = ""; // Revert to default
		}, 1500);

		// The calling function will update dataset.originalTitle and other UI parts
		console.log(`Title for ${conversationId} updated to "${newTitle}"`);
	} catch (error) {
		console.error("Failed to update title:", error);
		// Use inputElement.parentElement for error message context, as input is inside .title-edit-container
		handleError(
			`Error updating title: ${error.message}`,
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
