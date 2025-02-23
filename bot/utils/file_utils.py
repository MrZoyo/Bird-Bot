# bot/utils/file_utils.py
import os
from typing import List, Tuple


def generate_file_tree(path: str, prefix: str = "") -> str:
    """
    Generate a tree-like directory structure report including file sizes

    Args:
        path: The root directory path to start generating tree from
        prefix: The current line prefix for formatting (used in recursion)

    Returns:
        A string containing the formatted directory tree
    """
    output = []
    # Get and sort directory contents
    entries = os.listdir(path)
    entries.sort()

    for i, entry in enumerate(entries):
        full_path = os.path.join(path, entry)
        is_last = i == len(entries) - 1

        # Choose appropriate prefix symbols
        curr_prefix = "└── " if is_last else "├── "

        if os.path.isdir(full_path):
            # Directory entry
            output.append(f"{prefix}{curr_prefix}{entry}/")
            # Process subdirectory with updated prefix
            next_prefix = prefix + ("    " if is_last else "│   ")
            output.append(generate_file_tree(full_path, next_prefix))
        else:
            # File entry with size
            size = os.path.getsize(full_path)
            size_str = f"({format_size(size)})"
            output.append(f"{prefix}{curr_prefix}{entry} {size_str}")

    return "\n".join(output)


def format_size(size: int) -> str:
    """
    Convert byte size to human-readable format

    Args:
        size: Size in bytes

    Returns:
        Formatted string with appropriate unit (B, KB, MB, GB, TB)
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.2f}{unit}"
        size /= 1024
    return f"{size:.2f}TB"