// ./async_example.js
window.qbe_promise = fetch("https://api.ipify.org?format=json")
	.then((response) => response.json())
	.then((data) => `Your IP address is: ${data.ip}`);
