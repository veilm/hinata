// Message action handlers - edit, save, archive, copy
import { authFetch } from "./auth.js";
import { renderMarkdown, escapeHtml } from "./markdown.js";
import {
	showToast,
	showCopyFeedback,
	clearErrorMessages,
	handleError,
	createActionButton,
	setButtonsDisabledState,
	updateGlobalActionButtonsState,
	showMessageInfoModal,
	jumpToLatestMessage,
} from "./ui-utils.js";
import {
	ICON_INFO,
	ICON_PENCIL,
	ICON_SPLIT,
	ICON_ARCHIVE,
	ICON_COPY,
	ICON_SAVE,
	ICON_X,
} from "./constants.js";
import { updateSplitButtonState } from "./message-input.js";

// Store references to functions to avoid circular dependency
let handleForkFromMessageRef = null;
let executeForkFromMessageRef = null;
let loadConversationDetailsRef = null;

function setForkFunctions(handleFork, executeFork) {
	handleForkFromMessageRef = handleFork;
	executeForkFromMessageRef = executeFork;
}

function setLoadConversationDetailsRef(fn) {
	loadConversationDetailsRef = fn;
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
		contentWrapperDiv.innerHTML = renderMarkdown(originalContent); // Restore/set content with proper formatting

		actionsDiv.innerHTML = ""; // Clear Save/Cancel buttons

		const infoButton = createActionButton(ICON_INFO, "btn-info", () => {
			const role = messageElement.dataset.role || "unknown";
			showMessageInfoModal(filename, originalContent, role);
		});
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

		const forkButton = createActionButton(ICON_SPLIT, "btn-fork", () => {
			const role = messageElement.dataset.role || "unknown";
			if (handleForkFromMessageRef) {
				handleForkFromMessageRef(conversationId, filename, role);
			} else {
				console.error("handleForkFromMessage not initialized");
			}
		});
		forkButton.title = "Fork from here";

		const archiveButton = createActionButton(ICON_ARCHIVE, "btn-archive", () =>
			handleArchiveMessage(messageElement, conversationId, filename, reasoning),
		);
		archiveButton.title = "Archive";

		const copyButton = createActionButton(ICON_COPY, "btn-copy", () =>
			handleCopyMessage(originalContent),
		);
		copyButton.title = "Copy";

		actionsDiv.appendChild(infoButton);
		actionsDiv.appendChild(copyButton);
		actionsDiv.appendChild(editButton);
		actionsDiv.appendChild(forkButton);
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

		// Add event listener for auto-resize
		textarea.addEventListener("input", () => {
			// Save current scroll position
			const scrollTop =
				window.pageYOffset || document.documentElement.scrollTop;

			// Adjust height on input
			textarea.style.height = "auto";
			textarea.style.height = `${textarea.scrollHeight}px`;

			// Restore scroll position
			window.scrollTo(0, scrollTop);
		});

		// Append textarea to DOM first
		contentWrapperDiv.appendChild(textarea);

		// Then calculate initial height after DOM insertion
		requestAnimationFrame(() => {
			textarea.style.height = "auto";
			textarea.style.height = `${textarea.scrollHeight}px`;
			textarea.focus();
		});

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
function toggleForkEditState(
	messageElement,
	contentWrapperDiv,
	actionsDiv,
	originalContent,
	conversationId,
	filename,
	messageRole,
) {
	const isForkEditing = messageElement.dataset.forkEditing === "true";

	if (isForkEditing) {
		// Switching from Fork-Edit to View (Cancel)
		contentWrapperDiv.innerHTML = renderMarkdown(originalContent); // Restore content with proper formatting

		actionsDiv.innerHTML = ""; // Clear Save/Cancel buttons

		// Restore normal action buttons
		const infoButton = createActionButton(ICON_INFO, "btn-info", () => {
			const role = messageElement.dataset.role || "unknown";
			showMessageInfoModal(filename, originalContent, role);
		});
		infoButton.title = "Info";

		const editButton = createActionButton(ICON_PENCIL, "btn-edit", () =>
			toggleEditState(
				messageElement,
				contentWrapperDiv,
				actionsDiv,
				originalContent,
				conversationId,
				filename,
			),
		);
		editButton.title = "Edit";

		const forkButton = createActionButton(ICON_SPLIT, "btn-fork", () => {
			if (handleForkFromMessageRef) {
				handleForkFromMessageRef(conversationId, filename, messageRole);
			} else {
				console.error("handleForkFromMessage not initialized");
			}
		});
		forkButton.title = "Fork from here";

		const archiveButton = createActionButton(ICON_ARCHIVE, "btn-archive", () =>
			handleArchiveMessage(messageElement, conversationId, filename),
		);
		archiveButton.title = "Archive";

		const copyButton = createActionButton(ICON_COPY, "btn-copy", () =>
			handleCopyMessage(originalContent),
		);
		copyButton.title = "Copy";

		actionsDiv.appendChild(infoButton);
		actionsDiv.appendChild(copyButton);
		actionsDiv.appendChild(editButton);
		actionsDiv.appendChild(forkButton);
		actionsDiv.appendChild(archiveButton);

		delete messageElement.dataset.forkEditing;
		delete messageElement.dataset.originalContentForFork;
		updateGlobalActionButtonsState();
	} else {
		// Switching from View to Fork-Edit
		messageElement.dataset.forkEditing = "true";
		messageElement.dataset.originalContentForFork = originalContent;

		contentWrapperDiv.innerHTML = ""; // Clear current text content
		const textarea = document.createElement("textarea");
		textarea.value = originalContent;

		// Add event listener for auto-resize
		textarea.addEventListener("input", () => {
			const scrollTop =
				window.pageYOffset || document.documentElement.scrollTop;
			textarea.style.height = "auto";
			textarea.style.height = `${textarea.scrollHeight}px`;
			window.scrollTo(0, scrollTop);
		});

		// Append textarea to DOM first
		contentWrapperDiv.appendChild(textarea);

		// Then calculate initial height after DOM insertion
		requestAnimationFrame(() => {
			textarea.style.height = "auto";
			textarea.style.height = `${textarea.scrollHeight}px`;
			textarea.focus();
		});

		actionsDiv.innerHTML = ""; // Clear current buttons

		// Create Save button that will fork
		const saveButton = createActionButton(ICON_SAVE, "btn-save", () =>
			handleForkSave(
				messageElement,
				contentWrapperDiv,
				actionsDiv,
				textarea,
				conversationId,
				filename,
				messageRole,
			),
		);
		saveButton.title = "Save and Fork";

		// Create Cancel button
		const cancelButton = createActionButton(ICON_X, "btn-cancel", () =>
			toggleForkEditState(
				messageElement,
				contentWrapperDiv,
				actionsDiv,
				messageElement.dataset.originalContentForFork,
				conversationId,
				filename,
				messageRole,
			),
		);
		cancelButton.title = "Cancel";

		actionsDiv.appendChild(saveButton);
		actionsDiv.appendChild(cancelButton);
		updateGlobalActionButtonsState();
	}
}
async function handleForkSave(
	messageElement,
	contentWrapperDiv,
	actionsDiv,
	textareaElement,
	conversationId,
	filename,
	messageRole,
) {
	const editedContent = textareaElement.value;

	// Clear previous errors
	clearErrorMessages(actionsDiv);

	// Disable Save/Cancel temporarily
	const buttons = actionsDiv.querySelectorAll("button");
	setButtonsDisabledState(Array.from(buttons), true);

	try {
		// Execute the fork with the edited content
		if (executeForkFromMessageRef) {
			await executeForkFromMessageRef(
				conversationId,
				filename,
				messageRole,
				editedContent,
			);
		} else {
			throw new Error("executeForkFromMessage not initialized");
		}
		// The executeForkFromMessage will redirect, so we don't need to update UI here
	} catch (error) {
		console.error("Error during fork:", error);
		handleError(`Error during fork: ${error.message}`, actionsDiv);
		// Re-enable buttons on error
		setButtonsDisabledState(Array.from(buttons), false);
	}
}
async function handleCopyMessage(content) {
	try {
		// Try modern clipboard API first
		if (navigator.clipboard && navigator.clipboard.writeText) {
			await navigator.clipboard.writeText(content);
			// Show temporary success feedback
			showCopyFeedback(true);
		} else {
			// Fallback for non-HTTPS or older browsers
			const textArea = document.createElement("textarea");
			textArea.value = content;
			textArea.style.position = "fixed";
			textArea.style.left = "-9999px";
			textArea.style.top = "-9999px";
			document.body.appendChild(textArea);
			textArea.focus();
			textArea.select();

			try {
				const successful = document.execCommand("copy");
				showCopyFeedback(successful);
			} catch (err) {
				console.error("Fallback copy failed:", err);
				showCopyFeedback(false);
			}

			document.body.removeChild(textArea);
		}
	} catch (err) {
		console.error("Copy failed:", err);
		showCopyFeedback(false);
	}
}

// showCopyFeedback is imported from ui-utils.js

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

		// Show success toast
		showToast("Message archived", "success");

		// Reload the conversation to update the "Deleted Messages" section
		if (loadConversationDetailsRef) {
			loadConversationDetailsRef(conversationId);
		} else {
			console.error("loadConversationDetails not initialized");
		}
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

		// Update the original content data attribute so fork uses the new content
		messageElement.dataset.originalContent = newContent;

		toggleEditState(
			messageElement,
			contentWrapperDiv,
			actionsDiv,
			newContent, // Pass the new content to be displayed and set as original
			conversationId,
			filename,
			reasoning,
		);

		// Show success toast
		showToast("Message saved", "success");
	} catch (error) {
		console.error("Error saving message:", error);
		handleError(`Error saving message: ${error.message}`, actionsDiv);
		// Re-enable Save/Cancel buttons on error
		setButtonsDisabledState(Array.from(saveCancelButtons), false);
	}
}

export {
	toggleEditState,
	toggleForkEditState,
	handleForkSave,
	handleCopyMessage,
	handleArchiveMessage,
	handleSaveMessage,
	setForkFunctions,
	setLoadConversationDetailsRef,
};
