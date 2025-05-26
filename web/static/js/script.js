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
		const data = await response.json();

		if (data.conversations && data.conversations.length > 0) {
			const ul = document.createElement("ul");
			data.conversations.forEach((convId) => {
				const li = document.createElement("li");
				const a = document.createElement("a");
				a.href = `/conversation-page/${encodeURIComponent(convId)}`;
				a.textContent = escapeHtml(convId);
				li.appendChild(a);
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
	const titleElem = document.getElementById("conversation-title");
	const messagesContainer = document.getElementById("messages-container");
	const otherFilesContainer = document.getElementById("other-files-container");

	// Update page title and heading
	const safeConvId = escapeHtml(conversationId);
	document.title = `Conversation: ${safeConvId}`;
	titleElem.textContent = `Conversation: ${safeConvId}`;

	try {
		const response = await fetch(
			`/api/conversation/${encodeURIComponent(conversationId)}`,
		);
		if (!response.ok) {
			throw new Error(`HTTP error! status: ${response.status}`);
		}
		const data = await response.json();

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

function handleError(message, container) {
	const targetContainer =
		container ||
		document.getElementById("conversation-list-container") ||
		document.body;
	const errorP = document.createElement("p");
	errorP.className = "error-message"; // Add a class for styling errors if needed
	errorP.style.color = "red";
	errorP.textContent = escapeHtml(message);
	if (
		targetContainer.firstChild &&
		targetContainer.firstChild.nodeName === "H1"
	) {
		targetContainer.firstChild.insertAdjacentElement("afterend", errorP);
	} else {
		targetContainer.prepend(errorP);
	}
}
