#!/usr/bin/env python3
"""
File Migration Script: CADData folder to Supabase Storage

This script migrates files from the local CADData folder structure to Supabase Storage.

Usage:
    python migrate_files_to_supabase.py --dry-run
    python migrate_files_to_supabase.py

Actual CADData Structure (legacy, moved to Legacy/PDM_Vault/):
    D:\PDM_Vault\CADData\
    ├── csp0030.prt          (CAD files in root)
    ├── csp0030.drw          (CAD drawings in root)
    ├── csp0030.asm          (CAD assemblies in root)
    ├── STEP\
    │   └── csp0030.step     (STEP exports)
    ├── DXF\
    │   └── csp0030_dxf.dxf  (Flat pattern DXF)
    ├── SVG\
    │   └── csp0030.svg      (Bend drawing SVG)
    ├── PDF\
    │   └── csp0030.pdf      (PDF drawings)
    ├── Neutral\             (Neutral files)
    ├── Archive\             (Archived files)
    ├── CheckIn\             (Incoming - skip)
    └── BOM\                 (BOM exports - skip)

Target Buckets:
    - pdm-cad: CAD source files (.prt, .asm, .drw)
    - pdm-exports: STEP, DXF, SVG files
    - pdm-drawings: PDF drawings
    - pdm-other: Other files

Storage Path Convention:
    {bucket}/{item_number}/{revision}/{iteration}/{filename}
    Example: pdm-cad/csp0030/A/1/csp0030.prt
"""

import os
import sys
import argparse
import logging
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple

# This will need supabase-py installed: pip install supabase
try:
    from supabase import create_client, Client
except ImportError:
    print("Please install supabase: pip install supabase")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Folders to skip during migration
SKIP_FOLDERS = {'CheckIn', 'BOM', 'ParameterUpdate', 'Release', 'Revise', 'Archive'}

# Folder to bucket mapping
FOLDER_BUCKET_MAP = {
    'STEP': 'pdm-exports',
    'DXF': 'pdm-exports',
    'SVG': 'pdm-exports',
    'PDF': 'pdm-drawings',
    'Neutral': 'pdm-other',
}

# File extension to bucket mapping (for root folder files)
EXTENSION_BUCKET_MAP = {
    '.prt': 'pdm-cad',
    '.asm': 'pdm-cad',
    '.drw': 'pdm-cad',
    '.step': 'pdm-exports',
    '.stp': 'pdm-exports',
    '.dxf': 'pdm-exports',
    '.svg': 'pdm-exports',
    '.pdf': 'pdm-drawings',
}

# File extension to file_type mapping
EXT_TO_FILE_TYPE = {
    '.prt': 'CAD',
    '.asm': 'CAD',
    '.drw': 'CAD',
    '.step': 'STEP',
    '.stp': 'STEP',
    '.dxf': 'DXF',
    '.svg': 'SVG',
    '.pdf': 'PDF',
    '.neu': 'OTHER',
}

# Item number pattern (3 letters + digits)
ITEM_PATTERN = re.compile(r'^([a-z]{2,3}\d+)', re.IGNORECASE)


def extract_item_number(filename: str) -> Optional[str]:
    """Extract item number from filename"""
    name = Path(filename).stem.lower()
    # Remove common suffixes
    for suffix in ['_dxf', '_flat', '_bend', '_asm', '_drw']:
        if name.endswith(suffix):
            name = name[:-len(suffix)]

    match = ITEM_PATTERN.match(name)
    if match:
        return match.group(1).lower()
    return None


class FileMigrator:
    def __init__(self, supabase_url: str, supabase_key: str, caddata_path: str, dry_run: bool = False):
        self.supabase: Client = create_client(supabase_url, supabase_key)
        self.caddata_path = Path(caddata_path)
        self.dry_run = dry_run
        self.stats = {
            'scanned': 0,
            'uploaded': 0,
            'skipped': 0,
            'errors': 0,
            'no_item': 0,
            'bytes_uploaded': 0
        }
        self.item_cache: Dict[str, Dict] = {}  # Cache item info

    def get_item_info(self, item_number: str) -> Optional[Dict]:
        """Get item info from database with caching"""
        if item_number in self.item_cache:
            return self.item_cache[item_number]

        try:
            result = self.supabase.table('items').select('id, revision, iteration').eq('item_number', item_number).single().execute()
            self.item_cache[item_number] = result.data
            return result.data
        except Exception:
            self.item_cache[item_number] = None
            return None

    def get_bucket_for_file(self, file_path: Path, parent_folder: str) -> str:
        """Determine which bucket a file should go into"""
        # Check if in a known subfolder
        if parent_folder in FOLDER_BUCKET_MAP:
            return FOLDER_BUCKET_MAP[parent_folder]

        # Otherwise use extension
        ext = file_path.suffix.lower()
        return EXTENSION_BUCKET_MAP.get(ext, 'pdm-other')

    def get_file_type(self, filename: str) -> str:
        """Determine file type from extension"""
        ext = Path(filename).suffix.lower()
        return EXT_TO_FILE_TYPE.get(ext, 'OTHER')

    def build_storage_path(self, item_number: str, revision: str, iteration: int, filename: str) -> str:
        """Build the storage path for a file"""
        return f"{item_number}/{revision}/{iteration}/{filename}"

    def upload_file(self, local_path: Path, bucket: str, storage_path: str) -> bool:
        """Upload a file to Supabase Storage"""
        try:
            size = local_path.stat().st_size

            if self.dry_run:
                logger.info(f"[DRY RUN] Would upload: {local_path.name} -> {bucket}/{storage_path} ({size:,} bytes)")
                self.stats['bytes_uploaded'] += size
                return True

            with open(local_path, 'rb') as f:
                file_data = f.read()

            self.supabase.storage.from_(bucket).upload(
                storage_path,
                file_data,
                {'upsert': 'true'}  # Overwrite if exists
            )

            self.stats['bytes_uploaded'] += size
            logger.info(f"Uploaded: {bucket}/{storage_path} ({size:,} bytes)")
            return True

        except Exception as e:
            logger.error(f"Failed to upload {local_path}: {e}")
            return False

    def update_file_record(self, item_id: str, filename: str, storage_path: str, file_size: int, file_type: str):
        """Update or create file record in database"""
        if self.dry_run:
            logger.debug(f"[DRY RUN] Would update/create file record: {filename}")
            return

        try:
            # Check if file record exists
            existing = self.supabase.table('files').select('id').eq('item_id', item_id).eq('file_name', filename).execute()

            if existing.data:
                # Update existing record
                self.supabase.table('files').update({
                    'file_path': storage_path,
                    'file_size': file_size
                }).eq('id', existing.data[0]['id']).execute()
            else:
                # Create new record
                self.supabase.table('files').insert({
                    'item_id': item_id,
                    'file_type': file_type,
                    'file_name': filename,
                    'file_path': storage_path,
                    'file_size': file_size
                }).execute()
        except Exception as e:
            logger.error(f"Failed to update file record for {filename}: {e}")

    def process_file(self, file_path: Path, parent_folder: str = '') -> bool:
        """Process a single file"""
        self.stats['scanned'] += 1
        filename = file_path.name

        # Extract item number from filename
        item_number = extract_item_number(filename)
        if not item_number:
            logger.debug(f"Could not extract item number from: {filename}")
            self.stats['no_item'] += 1
            return False

        # Get item info from database
        item_info = self.get_item_info(item_number)
        if not item_info:
            logger.debug(f"Item {item_number} not found in database, skipping {filename}")
            self.stats['no_item'] += 1
            return False

        revision = item_info.get('revision', 'A')
        iteration = item_info.get('iteration', 1)
        item_id = item_info['id']

        # Determine bucket and storage path
        bucket = self.get_bucket_for_file(file_path, parent_folder)
        storage_path = self.build_storage_path(item_number, revision, iteration, filename)
        file_type = self.get_file_type(filename)
        file_size = file_path.stat().st_size

        # Upload file
        if self.upload_file(file_path, bucket, storage_path):
            self.update_file_record(item_id, filename, f"{bucket}/{storage_path}", file_size, file_type)
            self.stats['uploaded'] += 1
            return True
        else:
            self.stats['errors'] += 1
            return False

    def process_folder(self, folder_path: Path, parent_folder: str = '') -> int:
        """Process all files in a folder"""
        uploaded = 0

        for entry in folder_path.iterdir():
            if entry.is_file():
                if self.process_file(entry, parent_folder):
                    uploaded += 1

        return uploaded

    def run(self):
        """Run the migration"""
        logger.info(f"Starting file migration from {self.caddata_path}")
        logger.info(f"Dry run: {self.dry_run}")

        if not self.caddata_path.exists():
            logger.error(f"CADData path does not exist: {self.caddata_path}")
            return

        # Process root folder (CAD files)
        logger.info("Processing root folder (CAD files)...")
        root_files = [f for f in self.caddata_path.iterdir() if f.is_file()]
        logger.info(f"Found {len(root_files)} files in root folder")
        for file_path in root_files:
            self.process_file(file_path, '')

        # Process subfolders
        subfolders = [f for f in self.caddata_path.iterdir() if f.is_dir() and f.name not in SKIP_FOLDERS]
        logger.info(f"Found {len(subfolders)} subfolders to process")

        for folder in subfolders:
            folder_name = folder.name
            logger.info(f"Processing folder: {folder_name}")
            files_in_folder = [f for f in folder.iterdir() if f.is_file()]
            logger.info(f"  Found {len(files_in_folder)} files")
            self.process_folder(folder, folder_name)

        # Print summary
        logger.info("=" * 60)
        logger.info("Migration Complete!")
        logger.info(f"  Files scanned:      {self.stats['scanned']:,}")
        logger.info(f"  Files uploaded:     {self.stats['uploaded']:,}")
        logger.info(f"  No item match:      {self.stats['no_item']:,}")
        logger.info(f"  Skipped:            {self.stats['skipped']:,}")
        logger.info(f"  Errors:             {self.stats['errors']:,}")
        logger.info(f"  Total bytes:        {self.stats['bytes_uploaded']:,}")
        logger.info(f"  Total size:         {self.stats['bytes_uploaded'] / (1024*1024):.1f} MB")


def main():
    parser = argparse.ArgumentParser(description='Migrate CADData files to Supabase Storage')
    parser.add_argument('--caddata-path', default=r'D:\PDM_Vault\CADData', help='Path to CADData folder')
    parser.add_argument('--supabase-url', default=os.environ.get('SUPABASE_URL'), help='Supabase URL')
    parser.add_argument('--supabase-key', default=os.environ.get('SUPABASE_SERVICE_KEY'), help='Supabase service key')
    parser.add_argument('--dry-run', action='store_true', help='Simulate migration without uploading')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not args.supabase_url or not args.supabase_key:
        logger.error("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set (via args or env vars)")
        sys.exit(1)

    migrator = FileMigrator(
        supabase_url=args.supabase_url,
        supabase_key=args.supabase_key,
        caddata_path=args.caddata_path,
        dry_run=args.dry_run
    )

    migrator.run()


if __name__ == '__main__':
    main()
