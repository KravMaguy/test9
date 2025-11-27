#!/usr/bin/env python3
"""
Preview first 10 rows of a CSV file.

Usage:
    python preview_csv.py <csv_file>
    python preview_csv.py loans.csv
"""

import sys
import csv


def preview_csv(file_path: str, rows: int = 10):
    """Print first N rows of a CSV file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if i >= rows:
                    break
                print(f"Row {i}: {row}")
    except FileNotFoundError:
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python preview_csv.py <csv_file>")
        sys.exit(1)
    
    preview_csv(sys.argv[1])
