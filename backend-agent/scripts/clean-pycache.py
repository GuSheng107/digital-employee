#!/usr/bin/env python3
import os
import shutil


def clean_pycache(root_dir):
    print(f"Cleaning __pycache__ directories in: {root_dir}\n")
    count = 0
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        if '__pycache__' in dirnames:
            pycache_path = os.path.join(dirpath, '__pycache__')
            print(f"Removing: {pycache_path}")
            shutil.rmtree(pycache_path)
            count += 1
    
    print(f"\nCleanup complete! Removed {count} __pycache__ directories.")


if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    clean_pycache(project_root)
