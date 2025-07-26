// State machine-based markdown parser for bold and italic
function parseMarkdownStateMachine(text) {
    // Don't escape HTML here - it should already be escaped
    const input = text;
    let result = [];
    let i = 0;
    
    // Stack to handle nesting
    let formatStack = [];
    
    while (i < input.length) {
        const char = input[i];
        
        if (char === '*' || char === '_') {
            // Look ahead to understand the marker pattern
            let markerCount = 1;
            let markerType = char;
            let j = i + 1;
            
            while (j < input.length && input[j] === markerType) {
                markerCount++;
                j++;
            }
            
            // Check if this could be an italic within a word
            const prevChar = i > 0 ? input[i - 1] : ' ';
            const nextChar = j < input.length ? input[j] : ' ';
            const isStartBoundary = i === 0 || /\s/.test(prevChar) || /[^\w]/.test(prevChar);
            const isEndBoundary = j >= input.length || /\s/.test(nextChar) || /[^\w]/.test(nextChar);
            // Asterisks can be used anywhere, underscores need word boundaries
            const canBeItalic = markerType === '*' || (isStartBoundary && isEndBoundary);
            
            // Try to match/close existing formats first
            let handled = false;
            
            // Check if we can close any open format
            for (let k = formatStack.length - 1; k >= 0 && !handled; k--) {
                const format = formatStack[k];
                if (format.marker === markerType) {
                    if (format.type === 'bold' && markerCount >= 2) {
                        // Close bold
                        result.push('</strong>');
                        formatStack.splice(k, 1);
                        i += 2;
                        handled = true;
                    } else if (format.type === 'italic' && markerCount >= 1) {
                        // For closing, we're less strict about boundaries
                        const canCloseItalic = markerType === '*' || isStartBoundary;
                        if (canCloseItalic) {
                            // Close italic
                            result.push('</em>');
                            formatStack.splice(k, 1);
                            i += 1;
                            handled = true;
                        }
                    }
                }
            }
            
            if (!handled) {
                // Try to open new format
                if (markerCount >= 3) {
                    // Triple marker: try to open bold+italic
                    result.push('<strong><em>');
                    formatStack.push({ type: 'bold', marker: markerType });
                    formatStack.push({ type: 'italic', marker: markerType });
                    i += 3;
                } else if (markerCount >= 2) {
                    // Double marker: open bold
                    result.push('<strong>');
                    formatStack.push({ type: 'bold', marker: markerType });
                    i += 2;
                } else if (canBeItalic) {
                    // Single marker: open italic if allowed
                    result.push('<em>');
                    formatStack.push({ type: 'italic', marker: markerType });
                    i += 1;
                } else {
                    // Can't use as marker, treat as regular character
                    result.push(char);
                    i++;
                }
            }
        } else {
            // Regular character
            result.push(char);
            i++;
        }
    }
    
    // Close any unclosed tags
    while (formatStack.length > 0) {
        const format = formatStack.pop();
        result.push(format.type === 'bold' ? '</strong>' : '</em>');
    }
    
    return result.join('');
}


// Enhanced markdown renderer using the state machine parser
function renderMarkdownImproved(text) {
    // First escape HTML to prevent XSS
    let html = escapeHtml(text);
    
    // Headers (h1-h6) - do these first
    html = html.replace(/^######\s+(.+)$/gm, "<h6>$1</h6>");
    html = html.replace(/^#####\s+(.+)$/gm, "<h5>$1</h5>");
    html = html.replace(/^####\s+(.+)$/gm, "<h4>$1</h4>");
    html = html.replace(/^###\s+(.+)$/gm, "<h3>$1</h3>");
    html = html.replace(/^##\s+(.+)$/gm, "<h2>$1</h2>");
    html = html.replace(/^#\s+(.+)$/gm, "<h1>$1</h1>");
    
    // Code blocks (```) - protect from further processing
    const codeBlocks = [];
    html = html.replace(/```([\s\S]*?)```/g, function(match, code) {
        const placeholder = `__CODE_BLOCK_${codeBlocks.length}__`;
        codeBlocks.push('<pre><code>' + code + '</code></pre>');
        return placeholder;
    });
    
    // Inline code (`) - protect from further processing
    const inlineCode = [];
    html = html.replace(/`([^`]+)`/g, function(match, code) {
        const placeholder = `__INLINE_CODE_${inlineCode.length}__`;
        inlineCode.push('<code>' + code + '</code>');
        return placeholder;
    });
    
    // Now parse bold and italic with the state machine
    html = parseMarkdownStateMachine(html);
    
    // Restore code blocks and inline code
    codeBlocks.forEach((code, i) => {
        html = html.replace(`__CODE_BLOCK_${i}__`, code);
    });
    inlineCode.forEach((code, i) => {
        html = html.replace(`__INLINE_CODE_${i}__`, code);
    });
    
    // Line breaks (two spaces at end of line or double newline)
    html = html.replace(/  \n/g, "<br>\n");
    html = html.replace(/\n\n/g, "</p><p>");
    
    // Wrap in paragraph tags if not already wrapped
    if (!html.startsWith('<')) {
        html = '<p>' + html + '</p>';
    }
    
    return html;
}

// Export for use in main script
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { renderMarkdownImproved, parseMarkdownStateMachine };
}