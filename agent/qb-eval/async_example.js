// ./async_example.js
const response = await fetch("https://api.ipify.org?format=json");
const data = await response.json();
console.log(`Your IP address is: ${data.ip}`);
