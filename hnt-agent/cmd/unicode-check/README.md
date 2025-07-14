# unicode-check

A diagnostic tool for the hnt-agent spinner Unicode detection system.

## Installation

From the hnt-agent directory:
```bash
./install-unicode-check.sh
```

Or manually:
```bash
go build -o unicode-check ./cmd/unicode-check
cp unicode-check ~/.local/bin/
```

## Usage

Basic usage:
```bash
unicode-check
```

Test different scenarios:
```bash
# Force ASCII only
NO_UNICODE=1 unicode-check

# Simulate Linux console
TERM=linux unicode-check

# Test non-UTF8 locale
LC_ALL=C LANG=C unicode-check

# Test unknown terminal
TERM=xterm-mono unicode-check
```

## What it shows

1. **Environment Variables**: NO_UNICODE, TERM, COLORTERM, locale settings
2. **Locale Detection**: Which locale variables are set and if they indicate UTF-8
3. **Terminal Detection**: Terminal type and whether it's recognized as modern
4. **Font Detection**: 
   - Whether fc-list is available
   - Which fonts support Legacy Computing symbols (U+1FB90)
   - Results of testing multiple Unicode characters
5. **Detection Flow**: Step-by-step logic of how the decision was made
6. **Final Result**: The detected Unicode support level and number of available spinners
7. **Spinner Filtering**: How many spinners contain complex Unicode

## Detection Logic

The system determines Unicode support level as follows:

1. **ASCII only** (25 spinners):
   - NO_UNICODE=1 is set, OR
   - No UTF-8 locale detected, OR
   - fc-list check completed but no suitable fonts found

2. **Basic Unicode** (25 spinners, box-drawing characters):
   - UTF-8 locale detected, AND
   - Either: Linux console terminal, OR no fonts with Legacy Computing support

3. **Full Unicode** (42 spinners, including Legacy Computing symbols):
   - UTF-8 locale detected, AND
   - Not Linux console, AND
   - Fonts supporting Legacy Computing symbols found

## Font Detection Details

The system uses `fc-list` to check for fonts containing specific Unicode characters:

### Known good fonts (checked by name):
- Cascadia Code/Mono (v2404.03+)
- GNU Unifont
- Fairfax HD
- legacy_computing font
- UNSCII
- Adwaita Mono

### Character testing:
Tests support for 4 characters from the Legacy Computing block:
- U+1FB90 (🮐)
- U+1FB95 (🮕)
- U+1FBA0 (🮠)
- U+1FBB0 (🮰)

If 3 or more are supported, Full Unicode is enabled.