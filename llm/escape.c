#define _POSIX_C_SOURCE 200809L  // Define POSIX standard for getopt/optind
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>  // For exit
#include <string.h>
#include <unistd.h>  // For getopt

#define MAX_TAG_BUFFER 50  // Max length for <[/]_*hnt-assistant> + extras

// State definitions
#define STATE_NORMAL 0
#define STATE_SEEN_LT 1          // Seen '<'
#define STATE_SEEN_SLASH 2       // Seen '</'
#define STATE_SEEN_UNDERSCORE 3  // Seen '<[/]_' possibly more underscores
#define STATE_CHECK_TAG 4        // Seen '<[/]_*h...' - reading tag name
#define STATE_EXPECT_GT 5        // Matched tag name fully, expect '>'

// --- Static State Variables (File Scope) ---
static int state = STATE_NORMAL;
static char buffer[MAX_TAG_BUFFER];
static int buffer_idx = 0;
static int is_closing = 0;
static int underscore_count = 0;
static char matched_tag_base[20] = "";
static int unescape_mode = 0;  // 0 for escape (default), 1 for unescape (-u)
// Note: Removed unused tag_name_len variable

// Forward declaration for reprocess_char_in_normal used within
// flush_buffer_and_reset
static void reprocess_char_in_normal(int current_char);

// --- Helper Functions ---

// Flushes the buffer to stdout and resets the state machine to NORMAL
static void flush_buffer_and_reset() {
	if (buffer_idx > 0) {
		fwrite(buffer, 1, buffer_idx, stdout);
	}
	buffer_idx = 0;
	state = STATE_NORMAL;
	is_closing = 0;
	underscore_count = 0;
	// tag_name_len removed
	matched_tag_base[0] = '\0';
}

// Processes a confirmed tag match, printing the modified tag based on mode
static void process_match() {
	if (unescape_mode) {  // Unescaping mode (-u)
		if (underscore_count > 0) {
			// Remove one underscore
			putchar('<');
			if (is_closing) {
				putchar('/');
			}
			for (int i = 0; i < underscore_count - 1; ++i) {
				putchar('_');
			}
			// Print the base tag name
			if (strcmp(matched_tag_base, "system") == 0)
				printf("hnt-system");
			else if (strcmp(matched_tag_base, "user") == 0)
				printf("hnt-user");
			else if (strcmp(matched_tag_base, "assistant") == 0)
				printf("hnt-assistant");
			putchar('>');
		} else {  // underscore_count == 0 in unescape mode - Warning!
			// Construct the tag string first for the message
			char found_tag[MAX_TAG_BUFFER];
			int len = 0;
			found_tag[len++] = '<';
			if (is_closing) {
				found_tag[len++] = '/';
			}
			const char *base_name_ptr = NULL;
			if (strcmp(matched_tag_base, "system") == 0)
				base_name_ptr = "hnt-system";
			else if (strcmp(matched_tag_base, "user") == 0)
				base_name_ptr = "hnt-user";
			else if (strcmp(matched_tag_base, "assistant") == 0)
				base_name_ptr = "hnt-assistant";

			// Copy base name if found (should always be found here)
			if (base_name_ptr) {
				strcpy(found_tag + len, base_name_ptr);
				len += strlen(base_name_ptr);
			}
			found_tag[len++] = '>';
			found_tag[len] = '\0';

			// Print warning to stderr
			fprintf(stderr, "Warning: Found unescaped tag '%s'\n", found_tag);

			// Print original tag to stdout (as is)
			putchar('<');
			if (is_closing) {
				putchar('/');
			}
			if (base_name_ptr) {  // Print base name again
				printf("%s", base_name_ptr);
			}
			putchar('>');
		}
	} else {  // Escaping mode (default)
		// Add one underscore
		putchar('<');
		if (is_closing) {
			putchar('/');
		}
		putchar('_');  // Add the extra underscore
		// Print existing underscores
		for (int i = 0; i < underscore_count; ++i) {
			putchar('_');
		}
		// Print the base tag name
		if (strcmp(matched_tag_base, "system") == 0)
			printf("hnt-system");
		else if (strcmp(matched_tag_base, "user") == 0)
			printf("hnt-user");
		else if (strcmp(matched_tag_base, "assistant") == 0)
			printf("hnt-assistant");
		putchar('>');
	}

	// Reset state after processing (common to both modes)
	buffer_idx = 0;
	state = STATE_NORMAL;
	is_closing = 0;
	underscore_count = 0;
	matched_tag_base[0] = '\0';
}

// Re-processes the current character 'c' in the NORMAL state
// Needed after flushing when the char causing the flush needs processing
static void reprocess_char_in_normal(int current_char) {
	if (current_char == EOF) return;  // Nothing to process

	if (current_char == '<') {
		state = STATE_SEEN_LT;
		buffer_idx = 0;
		buffer[buffer_idx++] = current_char;
		is_closing = 0;
		underscore_count = 0;
		// tag_name_len removed
		matched_tag_base[0] = '\0';
	} else {
		putchar(current_char);
		state = STATE_NORMAL;  // Ensure state is normal
	}
}

int main(int argc, char *argv[]) {
	int c;
	int opt;

	// Parse command-line options
	// opterr = 0; // Uncomment to disable getopt's default error messages
	while ((opt = getopt(argc, argv, "u")) != -1) {
		switch (opt) {
			case 'u':
				unescape_mode = 1;
				break;
			default: /* '?' */
				fprintf(stderr, "Usage: %s [-u]\n", argv[0]);
				fprintf(stderr,
				        "  Processes stdin to stdout, escaping or "
				        "unescaping special tags.\n");
				fprintf(stderr,
				        "  Default mode adds one leading underscore "
				        "to tags like <_hnt-system>.\n");
				fprintf(stderr,
				        "  -u: Unescape mode (removes one leading "
				        "underscore from tags).\n");
				fprintf(stderr,
				        "      Warns on stderr if tag has no "
				        "underscores to remove.\n");
				exit(EXIT_FAILURE);
		}
	}

	// Check for non-option arguments (we don't process files, only stdin)
	if (optind < argc) {
		fprintf(stderr, "Error: Unexpected arguments found: ");
		for (int i = optind; i < argc; i++) {
			fprintf(stderr, "%s ", argv[i]);
		}
		fprintf(stderr, "\nUsage: %s [-u]\n", argv[0]);
		exit(EXIT_FAILURE);
	}

	// State variables are now static globals

	// --- Main Loop ---
	while ((c = getchar()) != EOF) {
		// Buffer overflow safeguard
		if (state != STATE_NORMAL && buffer_idx >= MAX_TAG_BUFFER - 1) {
			fprintf(stderr,
			        "Warning: Potential tag exceeded buffer size (%d), "
			        "flushing buffer.\n",
			        MAX_TAG_BUFFER);
			// Add current char to buffer before flushing if possible? Risky.
			// Flush first.
			int char_to_reprocess = c;
			flush_buffer_and_reset();
			// Now reprocess the character that caused the overflow check
			reprocess_char_in_normal(char_to_reprocess);
			continue;  // Skip the rest of the loop for this char
		}

		// --- State Machine ---
		switch (state) {
			case STATE_NORMAL:
				if (c == '<') {
					state = STATE_SEEN_LT;
					buffer_idx = 0;
					buffer[buffer_idx++] = c;
					is_closing = 0;
					underscore_count = 0;
					// tag_name_len removed
					matched_tag_base[0] = '\0';
				} else {
					putchar(c);
				}
				break;

			case STATE_SEEN_LT:  // Just seen '<'
				buffer[buffer_idx++] = c;
				if (c == '/') {
					is_closing = 1;
					state = STATE_SEEN_SLASH;
				} else if (c == '_') {
					underscore_count = 1;
					state = STATE_SEEN_UNDERSCORE;
				} else if (c == 'h') {        // Check for exact lowercase 'h'
					state = STATE_CHECK_TAG;  // Start checking tag name
				} else {
					// Character broke the sequence after '<'.
					// It was added to buffer above. Flush buffer as-is.
					flush_buffer_and_reset();
					// Do NOT reprocess 'c'.
				}
				break;

			case STATE_SEEN_SLASH:  // Just seen '</'
				buffer[buffer_idx++] = c;
				if (c == '_') {
					underscore_count = 1;
					state = STATE_SEEN_UNDERSCORE;
				} else if (c == 'h') {  // Check for exact lowercase 'h'
					state = STATE_CHECK_TAG;
				} else {
					// Character broke the sequence after '</'.
					// It was added to buffer above. Flush buffer as-is.
					flush_buffer_and_reset();
					// Do NOT reprocess 'c'.
				}
				break;

			case STATE_SEEN_UNDERSCORE:  // Seen '<[/]_' or '<[/]__...'
				buffer[buffer_idx++] = c;
				if (c == '_') {
					underscore_count++;
					// Stay in this state
				} else if (c == 'h') {  // Check for exact lowercase 'h'
					state = STATE_CHECK_TAG;
				} else {
					// Character broke the sequence after '<[/]_..._'.
					// It was added to buffer above. Flush buffer as-is.
					flush_buffer_and_reset();
					// Do NOT reprocess 'c'.
				}
				break;

			case STATE_CHECK_TAG:  // Reading potential tag name after '<[/]_*'
			                       // part
				if (isalnum(c) || c == '-') {
					buffer[buffer_idx++] = c;  // Add char to buffer

					// Check if current buffer content (the tag name part)
					// matches a known tag
					int tag_name_start_idx =
					    1 + (is_closing ? 1 : 0) + underscore_count;
					int current_tag_name_len = buffer_idx - tag_name_start_idx;

					if (current_tag_name_len > 0) {
						char
						    current_tag_name[MAX_TAG_BUFFER];  // Temp buffer
						                                       // for comparison
						strncpy(current_tag_name, buffer + tag_name_start_idx,
						        current_tag_name_len);
						current_tag_name[current_tag_name_len] = '\0';

						// Removed lowercase conversion - comparison is now
						// case-sensitive for(int i = 0; current_tag_name[i];
						// i++){
						//   current_tag_name[i] = tolower(current_tag_name[i]);
						// }

						const char *target_tags[] = {"hnt-system", "hnt-user",
						                             "hnt-assistant"};
						const char *base_names[] = {"system", "user",
						                            "assistant"};
						int target_tag_lengths[] = {10, 8, 13};
						int prefix_match_found = 0;
						// Removed unused full_match_found variable

						for (int i = 0; i < 3; ++i) {
							if (current_tag_name_len == target_tag_lengths[i] &&
							    strcmp(current_tag_name, target_tags[i]) == 0) {
								// Full match found!
								strcpy(matched_tag_base, base_names[i]);
								// tag_name_len removed
								state =
								    STATE_EXPECT_GT;  // Next char must be '>'
								// full_match_found removed
								prefix_match_found =
								    1;  // A full match is also a prefix match
								break;  // No need to check others once a full
								        // match is found
							} else if (current_tag_name_len <
							               target_tag_lengths[i] &&
							           strncmp(current_tag_name, target_tags[i],
							                   current_tag_name_len) == 0) {
								// This is a prefix of a known tag. Stay in
								// STATE_CHECK_TAG.
								prefix_match_found = 1;
								// Don't break, maybe it fully matches a shorter
								// tag later or fails completely
							}
						}

						// If the current tag name length exceeds the longest
						// possible tag, it can't match
						if (current_tag_name_len > 13) {
							prefix_match_found = 0;  // No longer a valid prefix
						}

						if (!prefix_match_found) {
							// The tag name being built doesn't match any known
							// prefix, so it cannot be one of our target tags.
							// Flush. The char 'c' that broke the match was
							// already added to the buffer before this check.
							flush_buffer_and_reset();  // Flushes buffer
							                           // including 'c', resets
							                           // state
							// DO NOT reprocess 'c' here, as it was just flushed
							// as part of the buffer.
						}
						// else: Stay in STATE_CHECK_TAG or transition to
						// STATE_EXPECT_GT (handled above)

					} else {  // Should not happen if first char was 'h'
						flush_buffer_and_reset();
						reprocess_char_in_normal(c);
					}

				} else if (c == '>') {
					// Got '>' but we weren't expecting it (didn't have a full
					// tag match)
					buffer[buffer_idx++] = c;  // Add '>' to buffer
					flush_buffer_and_reset();  // Flush buffer as-is
				} else {
					// Character is not valid for a tag name (and not '>')
					flush_buffer_and_reset();
					reprocess_char_in_normal(c);
				}
				break;  // End of STATE_CHECK_TAG

			case STATE_EXPECT_GT:  // Matched a full tag name, expecting '>'
				if (c == '>') {
					// Correct closing character found. Process the matched tag.
					process_match();
				} else {
					// Didn't get '>', sequence is invalid for our target tags.
					// Add the unexpected character to the buffer before
					// flushing.
					buffer[buffer_idx++] = c;
					// Flush the buffer (which contains the full matched tag + invalid char 'c').
					flush_buffer_and_reset();
					// Do NOT reprocess 'c', it was just flushed.
				}
				break;

			default:
				// Should ideally not happen
				fprintf(stderr,
				        "Error: Unknown state %d encountered with char '%c'. "
				        "Resetting.\n",
				        state, c);
				flush_buffer_and_reset();     // Attempt recovery by flushing
				reprocess_char_in_normal(c);  // Process current char normally
				break;
		}  // End switch

	}  // End while loop

	// After EOF, if we were in the middle of parsing a tag, flush the buffer
	if (state != STATE_NORMAL) {
		flush_buffer_and_reset();
	}

	return 0;
}
