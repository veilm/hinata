// Main entry point - wires all modules together
import { checkAuth, setupLogout, displayUsername } from "./modules/auth.js";
import {
	loadConversationsList,
	handleCreateConversation,
	loadConversationDetails,
} from "./modules/conversation.js";
import { handleError } from "./modules/ui-utils.js";

// Main initialization
document.addEventListener("DOMContentLoaded", () => {
	// Check if logged in
	if (!checkAuth()) {
		return;
	}

	// Setup UI
	displayUsername();
	setupLogout();

	// Global click handler for dropdown menus
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

	// Route handling
	const path = window.location.pathname;

	if (path === "/") {
		// Conversations list page
		loadConversationsList();
		const createBtn = document.getElementById("create-conversation-btn");
		if (createBtn) {
			createBtn.addEventListener("click", handleCreateConversation);
		}
	} else if (path.startsWith("/c/")) {
		// Conversation detail page
		const parts = path.split("/");
		const conversationId = parts[parts.length - 1];
		if (conversationId) {
			loadConversationDetails(conversationId);
			// setupMessageInputArea will be called from within loadConversationDetails
		} else {
			handleError("Conversation ID missing in URL.");
		}
	}
});
