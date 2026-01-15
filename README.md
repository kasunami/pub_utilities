# pub_utilities

A collection of utility scripts for various tasks.

## Scripts

### api/check_gemini_keys.py

Validates Gemini API keys and checks their remaining quota by making test requests to the Google Generative Language API.

#### Requirements

- Python 3.x (uses only standard library)

#### Usage

**Check a single key:**
```bash
./api/check_gemini_keys.py "YOUR_API_KEY_HERE"
# or
./api/check_gemini_keys.py --key "YOUR_API_KEY_HERE"
```

**Check multiple keys from a file:**
```bash
./api/check_gemini_keys.py keys.txt
```

The file should contain one API key per line.

#### Options

- `-k, --key`: Single API key string to check
- `-m, --model`: Model ID to use (default: `gemini-3-pro-preview`)
- `-p, --prompt`: Custom prompt text for test request (default: `Whatup, Dawg??`)
- `-w, --max-workers`: Maximum concurrent requests (default: 4)
- `--min-interval`: Minimum seconds between starting requests (default: 1.0)

#### Examples

```bash
# Check a single key with custom model
./api/check_gemini_keys.py --key "YOUR_KEY" --model "gemini-pro"

# Check keys from file with 2 concurrent workers
./api/check_gemini_keys.py keys.txt --max-workers 2

# Check with custom prompt and rate limiting
./api/check_gemini_keys.py keys.txt --prompt "Hello" --min-interval 2.0
```

#### Output

The script displays progress for each key checked and outputs:
- Number of passed/failed keys
- Response text for each key
- List of active keys with remaining usage

## License

See [LICENSE](LICENSE) file for details.
