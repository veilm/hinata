// Share functionality
import { authFetch } from "./auth.js";
import { escapeHtml } from "./markdown.js";

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

export { showShareModal };
