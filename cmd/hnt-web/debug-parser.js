#!/usr/bin/env node

// Load the parsers
const fs = require('fs');

// Mock browser environment
global.escapeHtml = function(str) {
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
};

// Load the simple parser
const simpleCode = fs.readFileSync('./markdown-parser-simple.js', 'utf8');
eval(simpleCode);

// Test cases
const tests = [
    // Basic
    { input: "**bold text**", expected: "<strong>bold text</strong>" },
    { input: "__bold text__", expected: "<strong>bold text</strong>" },
    { input: "*italic text*", expected: "<em>italic text</em>" },
    { input: "_italic text_", expected: "<em>italic text</em>" },
    
    // Complex
    { input: "**bold *italic* text**", expected: "<strong>bold <em>italic</em> text</strong>" },
    { input: "*italic **bold** text*", expected: "<em>italic <strong>bold</strong> text</em>" },
    { input: "**bold _italic_ text**", expected: "<strong>bold <em>italic</em> text</strong>" },
    { input: "_italic __bold__ text_", expected: "<em>italic <strong>bold</strong> text</em>" },
    { input: "***bold and italic***", expected: "<strong><em>bold and italic</em></strong>" },
    { input: "**bold with * asterisk**", expected: "<strong>bold with * asterisk</strong>" },
    
    // Edge cases
    { input: "**bold** and **more bold**", expected: "<strong>bold</strong> and <strong>more bold</strong>" },
    { input: "un*believ*able", expected: "un<em>believ</em>able" },
    { input: "**unclosed bold", expected: "<strong>unclosed bold</strong>" },
    { input: "*unclosed italic", expected: "<em>unclosed italic</em>" },
];

console.log('Testing Simple Parser\n');

let passed = 0;
tests.forEach((test, i) => {
    const result = renderMarkdownSimple(test.input);
    const isPass = result === test.expected;
    if (isPass) passed++;
    
    console.log(`Test ${i + 1}: ${test.input}`);
    console.log(`  Expected: ${test.expected}`);
    console.log(`  Got:      ${result}`);
    console.log(`  Status:   ${isPass ? '✓ PASS' : '✗ FAIL'}`);
    console.log();
});

console.log(`\nResults: ${passed}/${tests.length} passed (${Math.round(passed/tests.length*100)}%)`);

// Debug specific failing case
console.log('\n--- DEBUG: _italic text_ ---');
const debugInput = '_italic text_';
console.log('Input:', debugInput);
console.log('parseMarkdownSimple result:', parseMarkdownSimple(escapeHtml(debugInput)));
console.log('renderMarkdownSimple result:', renderMarkdownSimple(debugInput));