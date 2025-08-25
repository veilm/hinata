// Authentication module
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

// Export the authFetch function
export { authFetch };

// Auth check and redirect
export function checkAuth() {
	if (!localStorage.getItem("username") || !localStorage.getItem("password")) {
		window.location.href = "/login.html";
		return false;
	}
	return true;
}

// Setup logout functionality
export function setupLogout() {
	const logoutBtn = document.getElementById("logout-btn");
	if (logoutBtn) {
		logoutBtn.addEventListener("click", () => {
			localStorage.removeItem("username");
			localStorage.removeItem("password");
			window.location.href = "/login.html";
		});
	}
}

// Display username
export function displayUsername() {
	const username = localStorage.getItem("username");
	const usernameDisplay = document.getElementById("username-display");
	if (usernameDisplay) {
		usernameDisplay.textContent = `Logged in as: ${username}`;
	}
}
