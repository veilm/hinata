// UI Utilities - Toast notifications, error handling, modals
import { escapeHtml } from "./markdown.js";
import { ICON_X } from "./constants.js";

// Toast notifications
export function showToast(message, type = "success") {
	const toast = document.createElement("div");
	toast.style.position = "fixed";
	toast.style.bottom = "20px";
	toast.style.right = "20px";
	toast.style.padding = "10px 20px";
	toast.style.borderRadius = "4px";
	toast.style.fontSize = "14px";
	toast.style.zIndex = "10000";
	toast.style.transition = "opacity 0.3s ease";
	toast.style.boxShadow = "0 2px 8px rgba(0, 0, 0, 0.3)";

	switch (type) {
		case "success":
			toast.style.backgroundColor = "#6ec8ff";
			toast.style.color = "#000";
			break;
		case "error":
			toast.style.backgroundColor = "#f44336";
			toast.style.color = "#fff";
			break;
		case "info":
			toast.style.backgroundColor = "#4a8ab7";
			toast.style.color = "#fff";
			break;
		default:
			toast.style.backgroundColor = "#6ec8ff";
			toast.style.color = "#000";
	}

	toast.textContent = message;
	document.body.appendChild(toast);

	setTimeout(() => {
		toast.style.opacity = "0";
		setTimeout(() => document.body.removeChild(toast), 300);
	}, 2000);
}

// Copy feedback
export function showCopyFeedback(success) {
	const toast = document.createElement("div");
	toast.style.position = "fixed";
	toast.style.bottom = "20px";
	toast.style.right = "20px";
	toast.style.padding = "10px 20px";
	toast.style.borderRadius = "4px";
	toast.style.color = "#fff";
	toast.style.fontSize = "14px";
	toast.style.zIndex = "10000";
	toast.style.transition = "opacity 0.3s ease";

	if (success) {
		toast.style.backgroundColor = "#6ec8ff";
		toast.style.color = "#000";
		toast.textContent = "Copied to clipboard!";
	} else {
		toast.style.backgroundColor = "#f44336";
		toast.style.color = "#fff";
		toast.textContent = "Copy failed";
	}

	document.body.appendChild(toast);

	setTimeout(() => {
		toast.style.opacity = "0";
		setTimeout(() => document.body.removeChild(toast), 300);
	}, 2000);
}

// Error handling
export function clearErrorMessages(container) {
	if (!container) return;
	const errorMessages = container.querySelectorAll(".error-message");
	errorMessages.forEach((msg) => msg.remove());
}

export function handleError(message, contextElement) {
	let targetContainer;
	if (contextElement) {
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
			document.getElementById("messages-container") ||
			document.body;
	}

	if (
		targetContainer &&
		typeof targetContainer.querySelectorAll === "function"
	) {
		if (targetContainer !== document.body) {
			clearErrorMessages(targetContainer);
		}
	}

	const errorP = document.createElement("p");
	errorP.className = "error-message";
	errorP.textContent = escapeHtml(message);

	if (targetContainer && targetContainer.tagName === "LI") {
		targetContainer.appendChild(errorP);
	} else if (
		targetContainer &&
		targetContainer.firstChild &&
		targetContainer.firstChild.nodeName === "H1"
	) {
		targetContainer.firstChild.insertAdjacentElement("afterend", errorP);
	} else if (targetContainer) {
		targetContainer.prepend(errorP);
	} else {
		document.body.appendChild(errorP);
	}
}

// Message info modal
export function showMessageInfoModal(filename, content, role = "unknown", fullPath = null) {
	const lineCount = content.split("\n").length;
	const charCount = content.length;

	const overlay = document.createElement("div");
	overlay.className = "info-modal-overlay";

	const modalContent = document.createElement("div");
	modalContent.className = "info-modal-content";

	// Build the HTML with reordered fields
	let infoHtml = `
		<p><strong>Type:</strong> ${escapeHtml(role.charAt(0).toUpperCase() + role.slice(1))}</p>
		<p><strong>Lines:</strong> ${lineCount}</p>
		<p><strong>Characters:</strong> ${charCount}</p>
	`;

	// Add Path if we have it
	if (fullPath) {
		infoHtml += `<p><strong>Path:</strong> ${escapeHtml(fullPath)}</p>`;
	}

	// Add File at the end
	infoHtml += `<p><strong>File:</strong> ${escapeHtml(filename)}</p>`;

	modalContent.innerHTML = infoHtml;

	const closeButton = document.createElement("button");
	closeButton.className = "info-modal-close";
	closeButton.innerHTML = ICON_X;

	const closeModal = () => {
		overlay.remove();
	};

	closeButton.addEventListener("click", closeModal);
	overlay.addEventListener("click", (e) => {
		if (e.target === overlay) {
			closeModal();
		}
	});

	modalContent.appendChild(closeButton);
	overlay.appendChild(modalContent);
	document.body.appendChild(overlay);
}

// Helper to create action buttons
export function createActionButton(svgIconHtml, className, onClick) {
	const button = document.createElement("button");
	button.type = "button";
	button.innerHTML = svgIconHtml;
	button.className = className;
	button.addEventListener("click", onClick);
	return button;
}

// Button state management
export function setButtonsDisabledState(buttons, disabled) {
	buttons.forEach((btn) => {
		if (btn) btn.disabled = disabled;
	});
}

// Jump to latest message
export function jumpToLatestMessage() {
	const messagesContainerElem = document.getElementById("messages-container");
	if (messagesContainerElem) {
		const messageElements = messagesContainerElem.querySelectorAll(
			".message:not(.archived-message)",
		);

		if (messageElements.length > 0) {
			const lastMessageElement = messageElements[messageElements.length - 1];
			const messageInputArea = document.getElementById("message-input-area");
			const inputAreaHeight = messageInputArea
				? messageInputArea.offsetHeight
				: 0;

			const rect = lastMessageElement.getBoundingClientRect();
			const absoluteBottom = rect.bottom + window.pageYOffset;
			const targetScroll =
				absoluteBottom - window.innerHeight + inputAreaHeight + 20;

			window.scrollTo({
				top: targetScroll,
				behavior: "smooth",
			});
		} else {
			const archiveContainer = document.querySelector(".archive-container");
			if (archiveContainer) {
				archiveContainer.scrollIntoView({
					behavior: "smooth",
					block: "start",
				});
			} else {
				window.scrollTo({
					top: 0,
					behavior: "smooth",
				});
			}
		}
	}
}

// Update global action buttons state
export function updateGlobalActionButtonsState() {
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
