#!/usr/bin/env python3
"""
Check tracked source files for null bytes and UTF-16 BOMs.
This script scans Python, HTML, JS, CSS, YAML, TOML, Markdown, TXT, and JSON files
for common corruption issues that cause startup crashes.
"""
import subprocess
import sys
from pathlib import Path

# File extensions to check
SOURCE_EXTENSIONS = {'.py', '.html', '.js', '.css', '.yml', '.yaml', '.toml', '.md', '.txt', '.json'}

# UTF-16 BOMs
UTF16_LE_BOM = b'\xff\xfe'
UTF16_BE_BOM = b'\xfe\xff'


def get_tracked_files():
    """Get all tracked files from git."""
    try:
        result = subprocess.run(
            ['git', 'ls-files'],
            capture_output=True,
            text=True,
            check=True
        )
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except subprocess.CalledProcessError as e:
        print(f"Error getting tracked files: {e}", file=sys.stderr)
        sys.exit(1)


def check_file(filepath):
    """
    Check a single file for null bytes and UTF-16 BOMs.
    Returns a tuple: (has_issue, issue_description)
    """
    path = Path(filepath)
    
    # Only check source files
    if path.suffix.lower() not in SOURCE_EXTENSIONS:
        return False, None
    
    # Skip if file doesn't exist (deleted or moved)
    if not path.exists():
        return False, None
    
    try:
        with open(path, 'rb') as f:
            content = f.read()
        
        # Check for UTF-16 BOMs
        if content.startswith(UTF16_LE_BOM):
            return True, "UTF-16 LE BOM detected"
        if content.startswith(UTF16_BE_BOM):
            return True, "UTF-16 BE BOM detected"
        
        # Check for null bytes
        if b'\x00' in content:
            null_positions = [i for i, byte in enumerate(content) if byte == 0]
            return True, f"Contains {len(null_positions)} null byte(s) at positions: {null_positions[:5]}..."
        
        return False, None
        
    except Exception as e:
        print(f"Warning: Could not read {filepath}: {e}", file=sys.stderr)
        return False, None


def main():
    """Main entry point."""
    print("Checking tracked source files for null bytes and UTF-16 BOMs...")
    print(f"   Extensions checked: {', '.join(sorted(SOURCE_EXTENSIONS))}\n")
    
    tracked_files = get_tracked_files()
    issues_found = []
    
    for filepath in tracked_files:
        has_issue, description = check_file(filepath)
        if has_issue:
            issues_found.append((filepath, description))
    
    if issues_found:
        print("ISSUES FOUND:\n")
        for filepath, description in issues_found:
            print(f"  {filepath}")
            print(f"    -> {description}\n")
        
        print(f"\nTotal: {len(issues_found)} file(s) with issues")
        sys.exit(1)
    else:
        print("All tracked source files are clean!")
        sys.exit(0)


if __name__ == '__main__':
    main()

