# Unicode Detection in hnt-agent

## Current Behavior (Detection OFF by default)

By default, hnt-agent assumes full Unicode support and uses all 42 spinners, including those with Legacy Computing symbols.

## Environment Variables

### `NO_UNICODE=1`
Force ASCII-only mode (25 spinners). This always takes precedence.

```bash
NO_UNICODE=1 hnt-agent
```

### `HINATA_ENABLE_UNICODE_DETECTION=1`
Enable automatic Unicode detection based on:
- Locale settings (UTF-8 required)
- Terminal type (Linux console gets basic Unicode)
- Font support via fc-list (checks for Legacy Computing symbols)

```bash
HINATA_ENABLE_UNICODE_DETECTION=1 hnt-agent
```

## Testing

Use the built-in diagnostic command:
```bash
hnt-agent unicode-check
```

Test different scenarios:
```bash
# Default (all spinners)
hnt-agent unicode-check

# Force ASCII
NO_UNICODE=1 hnt-agent unicode-check

# Enable detection
HINATA_ENABLE_UNICODE_DETECTION=1 hnt-agent unicode-check

# Test detection with different terminals
HINATA_ENABLE_UNICODE_DETECTION=1 TERM=linux hnt-agent unicode-check
```

## Unicode Support Levels

1. **ASCII only** (25 spinners): Simple characters like `|`, `/`, `-`, `\`
2. **Basic Unicode** (25 spinners): Includes box-drawing characters
3. **Full Unicode** (42 spinners): Includes Legacy Computing symbols

## Future

Once testing confirms the detection works well across different systems, set `HINATA_ENABLE_UNICODE_DETECTION=1` to make detection the default behavior.